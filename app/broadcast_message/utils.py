import inspect
import json
from datetime import datetime, timezone
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from emergency_alerts_utils.clients.zendesk.zendesk_client import (
    EASSupportTicket,
)
from emergency_alerts_utils.xml.common import SENDER
from flask import current_app
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform

from app import zendesk_client
from app.clients.email_client import EmailClient
from app.dao.dao_utils import dao_save_object
from app.errors import InvalidRequest
from app.models import (
    BroadcastEvent,
    BroadcastEventMessageType,
    BroadcastStatusType,
)
from app.tasks.broadcast_message_tasks import send_broadcast_event


def update_broadcast_message_status(
    broadcast_message, new_status, updating_user=None, api_key_id=None, rejection_reason=None
):
    _validate_broadcast_update(broadcast_message, new_status, updating_user)

    if new_status == BroadcastStatusType.BROADCASTING:
        broadcast_message.approved_at = datetime.now(timezone.utc)
        broadcast_message.approved_by = updating_user

    if new_status == BroadcastStatusType.CANCELLED:
        broadcast_message.cancelled_at = datetime.now(timezone.utc)
        broadcast_message.cancelled_by = updating_user
        broadcast_message.cancelled_by_api_key_id = api_key_id

    if new_status == BroadcastStatusType.REJECTED:
        broadcast_message.rejected_at = datetime.now(timezone.utc)
        broadcast_message.rejected_by = updating_user
        broadcast_message.rejection_reason = rejection_reason
        broadcast_message.rejected_by_api_key_id = api_key_id

    if new_status == BroadcastStatusType.PENDING_APPROVAL:
        # Check here to see if same user was creator
        broadcast_message.submitted_at = datetime.now(timezone.utc)
        broadcast_message.submitted_by = updating_user

    current_app.logger.info(
        f"broadcast_message {broadcast_message.id} moving from {broadcast_message.status} to {new_status}"
    )
    broadcast_message.status = new_status

    dao_save_object(broadcast_message)
    _create_p1_zendesk_alert(broadcast_message)

    if new_status in {BroadcastStatusType.BROADCASTING, BroadcastStatusType.CANCELLED}:
        _create_broadcast_event(broadcast_message)


def _validate_broadcast_update(broadcast_message, new_status, updating_user):
    if new_status not in BroadcastStatusType.ALLOWED_STATUS_TRANSITIONS[broadcast_message.status]:
        raise InvalidRequest(
            f"Cannot move broadcast_message {broadcast_message.id} from {broadcast_message.status} to {new_status}",
            status_code=400,
        )

    if new_status == BroadcastStatusType.BROADCASTING:
        # training mode services can approve their own broadcasts
        if updating_user == broadcast_message.submitted_by and not broadcast_message.service.restricted:
            raise InvalidRequest(
                "You cannot approve an alert that you submitted for approval.",
                status_code=400,
            )
        elif len(broadcast_message.areas["simple_polygons"]) == 0:
            raise InvalidRequest(
                f"broadcast_message {broadcast_message.id} has no selected areas and so cannot be broadcasted.",
                status_code=400,
            )


def _create_p1_zendesk_alert(broadcast_message):
    if not current_app.is_prod:
        return

    if broadcast_message.status != BroadcastStatusType.BROADCASTING:
        return

    if broadcast_message.stubbed:
        return

    message = inspect.cleandoc(f"""
        Broadcast Sent

        https://www.notifications.service.gov.uk/services/{broadcast_message.service_id}/current-alerts/{broadcast_message.id}

        Sent on channel {broadcast_message.service.broadcast_channel} to {broadcast_message.areas["names"]}.

        Content starts "{broadcast_message.content[:100]}".
    """)

    ticket = EASSupportTicket(
        subject="Live broadcast sent",
        message=message,
        ticket_type=EASSupportTicket.TYPE_INCIDENT,
        technical_ticket=True,
        org_id=current_app.config["BROADCAST_ORGANISATION_ID"],
        org_type="central",
        service_id=str(broadcast_message.service_id),
        p1=True,
    )
    zendesk_client.send_ticket_to_zendesk(ticket)


def _create_broadcast_event(broadcast_message):
    """
    If the service is live and the broadcast message is not stubbed, creates a broadcast event, stores it in the
    database, and triggers the task to send the CAP XML off.
    """
    service = broadcast_message.service

    if not broadcast_message.stubbed and not service.restricted:
        msg_types = {
            BroadcastStatusType.BROADCASTING: BroadcastEventMessageType.ALERT,
            BroadcastStatusType.CANCELLED: BroadcastEventMessageType.CANCEL,
        }
        event = BroadcastEvent(
            service=service,
            broadcast_message=broadcast_message,
            message_type=msg_types[broadcast_message.status],
            transmitted_content={"body": broadcast_message.content},
            transmitted_areas=broadcast_message.areas,
            transmitted_sender=SENDER,
            # TODO: Should this be set to now? Or the original starts_at?
            transmitted_starts_at=broadcast_message.starts_at,
            transmitted_finishes_at=broadcast_message.finishes_at,
        )
        dao_save_object(event)
        broadcast_task = send_broadcast_event.send(broadcast_event_id=str(event.id))
        current_app.logger.info("Enqueued broadcast task: %s", broadcast_task.asdict())
    elif broadcast_message.stubbed != service.restricted:
        # It's possible for a service to create a broadcast in trial mode, and then approve it after the
        # service is live (or vice versa). We don't think it's safe to send such broadcasts, as the service
        # has changed since they were created. Log an error instead.
        current_app.logger.error(
            f"Broadcast event not created. Stubbed status of broadcast message was {broadcast_message.stubbed}"
            f' but service was {"in trial mode" if service.restricted else "live"}'
        )


def send_alert_summary_email(broadcast_message, data):
    service = broadcast_message.service
    alert_notification_addresses = service.alert_notification_addresses
    bcc_addresses = [se.email_address for se in alert_notification_addresses]
    subject = f"{service.name} advance notice of broadcast"
    text_body, html_body = _build_alert_summary_email_bodies(
        {
            "broadcast_message": broadcast_message,
            "data": data,
            "env": current_app.config["ENVIRONMENT"],
        }
    )
    attachments = _build_alert_summary_email_attachments(data)

    geojson_obj = data.get("geojson")
    geojson_str = json.dumps(geojson_obj)

    png_bytes = _geojson_to_miniscale_png(geojson_str)

    client = EmailClient()
    response = client.send_email(
        subject=subject,
        bcc_addresses=bcc_addresses,
        text_body=text_body,
        html_body=html_body,
        attachments=attachments,
        image=png_bytes,
    )
    return response


def _build_alert_summary_email_bodies(data):
    env = Environment(loader=FileSystemLoader("app/broadcast_message/email_template"))
    html_body = env.get_template("alert_summary.html").render(data)
    text_body = env.get_template("alert_summary.txt").render(data)

    # Normalize text_body to CRLF and ensure final CRLF
    text_body = text_body.replace("\n", "\r\n")
    if not text_body.endswith("\r\n"):
        text_body += "\r\n"

    return text_body, html_body


def _build_alert_summary_email_attachments(data):
    """
    Generate attachments for a broadcast message summary email.
    """
    geojson = data.get("geojson")
    cap_xml = data.get("cap_xml")
    ibag_xml = data.get("ibag_xml")

    attachments = []

    if geojson:
        attachments.append(("areas.geojson", json.dumps(geojson), "application/geo+json"))
    if cap_xml:
        attachments.append(("areas.cap.xml", cap_xml, "application/xml"))
    if ibag_xml:
        attachments.append(("areas.ibag.xml", ibag_xml, "application/xml"))

    return attachments


def _geojson_to_miniscale_png(
    geojson_str: str,
    miniscale_path: str = "MiniScale_standard_3857.tif",
    padding_ratio: float = 0.1,
):
    """
    Render a GeoJSON polygon on top of the MiniScale Web Mercator raster.
    Requires MiniScale_standard_3857.tif already converted to EPSG:3857.
    """
    # Check bucket and map file exists
    bucket = current_app.config.get("MINISCALE_MAP_S3_BUCKET_NAME")
    if not bucket:
        current_app.logger.error("MINISCALE_MAP_S3_BUCKET_NAME not set in config")
        return None

    s3 = boto3.client("s3")
    key = "map.tif"

    # Read MiniScale raster map file into memory
    try:
        buf = BytesIO()
        s3.download_fileobj(bucket, key, buf)
        buf.seek(0)
        base = Image.open(buf).convert("RGBA")

    except ClientError as e:
        current_app.logger.error(f"Failed to download MiniScale map '{key}' from bucket '{bucket}': {e}")
        return None

    except Exception as e:
        current_app.logger.error(f"Failed to load MiniScale TIFF from S3: {e}")
        return None

    width, height = base.size

    # Web Mercator bounds
    wm_left = -1057132.938
    wm_top = 8760625.698
    wm_right = 404592.962
    wm_bottom = 6405960.394

    # lon/lat → Web Mercator transformer
    to_wm = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    # Parse GeoJSON
    data = json.loads(geojson_str)

    if data["type"] == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in data["features"]]
    elif data["type"] == "Feature":
        geoms = [shape(data["geometry"])]
    else:
        geoms = [shape(data)]

    # Union geometry and convert to Web Mercator
    full_geom = geoms[0]
    for g in geoms[1:]:
        full_geom = full_geom.union(g)

    def proj_xy(x, y, z=None):
        return to_wm.transform(x, y)

    geom_wm = transform(proj_xy, full_geom)

    # Bounding box in Web Mercator
    minx, miny, maxx, maxy = geom_wm.bounds

    # Add padding
    dx = (maxx - minx) * padding_ratio
    dy = (maxy - miny) * padding_ratio
    minx -= dx
    maxx += dx
    miny -= dy
    maxy += dy

    # Convert WM → pixel coordinates
    def wm_to_px(x, y):
        px = int((x - wm_left) / (wm_right - wm_left) * width)
        py = int((wm_top - y) / (wm_top - wm_bottom) * height)
        return px, py

    # Crop MiniScale to bounding box
    px_min, py_min = wm_to_px(minx, maxy)
    px_max, py_max = wm_to_px(maxx, miny)

    cropped = base.crop((px_min, py_min, px_max, py_max))

    # Draw polygons with proper opacity using a transparent overlay
    overlay = Image.new("RGBA", cropped.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Draw polygons
    for g in geoms:
        g_wm = transform(proj_xy, g)

        if isinstance(g_wm, Polygon):
            # Exterior ring
            rings = [g_wm.exterior.coords]
            # Interior rings
            for interior in g_wm.interiors:
                rings.append(interior.coords)
        elif isinstance(g_wm, MultiPolygon):
            rings = []
            for poly in g_wm.geoms:
                rings.append(poly.exterior.coords)
                for interior in poly.interiors:
                    rings.append(interior.coords)
        else:
            # Not a polygon (LineString, Point, etc.)
            continue

        for ring in rings:
            pts = [wm_to_px(x, y) for x, y in ring]
            pts = [(x - px_min, y - py_min) for x, y in pts]

            # Semi‑transparent light blue fill + solid outline
            overlay_draw.polygon(pts, fill=(180, 200, 220, 205), outline=(0, 0, 0, 0))

            # Increase outline width
            overlay_draw.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=12)

    # Composite overlay onto the cropped basemap
    cropped = Image.alpha_composite(cropped, overlay)

    # Save the image in memory and return the bytes
    buf = BytesIO()
    cropped.save(buf, "PNG")
    buf.seek(0)
    return buf.getvalue()
