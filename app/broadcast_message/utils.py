import inspect
import json
from datetime import datetime, timezone

from emergency_alerts_utils.clients.zendesk.zendesk_client import (
    EASSupportTicket,
)
from emergency_alerts_utils.xml.common import SENDER
from flask import current_app

from app import zendesk_client
from app.clients.ses_client import SESClient
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


def send_alert_summary_email(broadcast_message, data, client=None):
    service = broadcast_message.service
    service_emails = service.email_addresses
    to_addresses = [se.email_address for se in service_emails]
    subject = f"{service.name} advance notice of broadcast"
    body = _build_alert_summary_email_body(broadcast_message, data)
    attachments = _build_alert_summary_email_attachments(data)

    ses = SESClient(client=client)
    ses.send_raw_email(subject=subject, to_addresses=to_addresses, html_body=body, attachments=attachments)


def _build_alert_summary_email_body(broadcast_message, data):
    """
    Generate an HTML summary email for a broadcast message.
    """

    alert_message = broadcast_message.content
    additional_info = broadcast_message.extra_content
    created_at = broadcast_message.created_at.replace(microsecond=0)
    created_by = broadcast_message.created_by.id
    duration_minutes = int(broadcast_message.duration.total_seconds() // 60)
    service_name = broadcast_message.service.name
    channel = broadcast_message.service.broadcast_channel
    count_of_phones = data.get("count_of_phones")
    currentenv = current_app.config["ENVIRONMENT"]

    # Build HTML
    html = f"""
    <html>
      <body style="margin:0; padding:0; font-family: Arial, Helvetica, sans-serif; background:#f3f2f1;">

        <div style="background:#0b0c0c; padding:16px;">
          <h1 style="color:#ffffff; margin:0; font-size:24px; font-weight:700;">
            GOV.UK Emergency Alerts - {currentenv}
          </h1>
        </div>

        <div style="padding:24px; background:#ffffff;">

          <h2 style="color:#0b0c0c; font-size:20px; margin-top:0;">
            Alert Summary
          </h2>

          <p style="font-size:16px; color:#0b0c0c;">
            <br>An alert will be sent from the <strong>{service_name}</strong>
            service with the following details.</br>
          </p>
          <p style="font-size:16px; color:#0b0c0c;">
            <br>The broadcast channel will be <strong>{channel}</strong>.</br>
          </p>

          <p style="font-size:16px; color:#0b0c0c;">
            <strong>Alert Message</strong><br>{alert_message}
          </p>

        <p style="font-size:16px; color:#0b0c0c;">
            <strong>Phone Estimate</strong><br>{count_of_phones}
          </p>
    """

    if additional_info:
        html += f"""
          <p style="font-size:16px; color:#0b0c0c;">
            <strong>Additional Info</strong><br>{additional_info}
          </p>
        """

    html += f"""
          <p style="font-size:16px; color:#0b0c0c;">
            <strong>Alert Duration</strong><br>{duration_minutes} minutes
          </p>

          <p style="font-size:16px; color:#0b0c0c;">
            <strong>Attachments</strong>
            <ul style="margin: 0 0 20px 20px; padding: 0; font-family: Arial, sans-serif;
              font-size: 16px; line-height: 1.5;">
              <li style="margin-bottom: 5px;">areas.geojson - areas covered by this alert, in GEOjson format</li>
              <li style="margin-bottom: 5px;">areas.cap.xml - areas covered by this alert, in CAP XML format</li>
              <li style="margin-bottom: 5px;">areas.ibag.xml - areas covered by this alert, in IBAG XML format</li>
            </ul>
          </p>

          <p style="font-size:16px; color:#0b0c0c;">
            If you require assistance, or wish to unsubscribe from future advance notice notifications please contact
            the <a href="mailto:emergency-alerts-support@digital.cabinet-office.gov.uk">Emergency Alerts Support</a>
            team.
          </p>
        </div>

        <div style="padding:16px; text-align:center; font-size:14px; color:#505a5f;">
          Alert created by {created_by} at {created_at}.
        </div>
      </body>
    </html>
    """

    return html


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
