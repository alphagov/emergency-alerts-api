from itertools import chain, combinations

from emergency_alerts_utils.api_key import KEY_TYPE_TEAM, KEY_TYPE_TEST
from emergency_alerts_utils.polygons import Polygons
from emergency_alerts_utils.template import BroadcastMessageTemplate
from flask import current_app, jsonify, make_response, request
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.validation import explain_validity
from sqlalchemy.orm.exc import MultipleResultsFound

from app import api_user, authenticated_service
from app.authentication.auth import AuthError
from app.broadcast_message import utils as broadcast_utils
from app.broadcast_message.translators import cap_xml_to_dict
from app.dao.broadcast_message_dao import (
    dao_get_broadcast_message_by_references_and_service_id,
)
from app.dao.dao_utils import dao_save_object
from app.models import BROADCAST_TYPE, BroadcastMessage, BroadcastStatusType
from app.schema_validation import validate
from app.v2.broadcast import v2_broadcast_blueprint
from app.v2.broadcast.broadcast_schemas import (
    cancel_broadcast_schema,
    post_broadcast_schema,
)
from app.v2.errors import BadRequestError, ValidationError
from app.xml_schemas import validate_xml


@v2_broadcast_blueprint.route("", methods=["POST"])
def create_broadcast():
    current_app.logger.info("/v2/broadcast API request received")
    _check_service_has_permission(
        BROADCAST_TYPE,
        authenticated_service.permissions,
    )
    _check_key_type_allowed(api_user.key_type)

    if request.content_type != "application/cap+xml":
        raise BadRequestError(
            message=f"Content type {request.content_type} not supported",
            status_code=415,
        )

    cap_xml = request.get_data()

    current_app.logger.info("Provided with CAP XML: %s", cap_xml)

    xml_validation_error = validate_xml(cap_xml, "CAP-v1.2.xsd")
    if xml_validation_error is not None:
        raise BadRequestError(
            message="Request data is not valid CAP XML: " + xml_validation_error,
            status_code=400,
        )

    broadcast_json = cap_xml_to_dict(cap_xml)

    if broadcast_json["msgType"] == "Cancel":
        # A Cancel only needs <references>; it doesn't carry the alert content an
        # Alert does, so validate against the slimmer schema and skip the Alert path.
        validate(broadcast_json, cancel_broadcast_schema)
        if broadcast_json["references"] is None:
            raise BadRequestError(
                message="Unable to cancel broadcast. Cap_xml is missing field: <references>",
                status_code=400,
            )
        broadcast_message = _cancel_or_reject_broadcast(
            broadcast_json["references"].split(","), authenticated_service.id
        )
        current_app.logger.info("Cancelled/rejected BroadcastMessage %s", broadcast_message.id)
        return jsonify(broadcast_message.serialize()), 201

    else:
        validate(broadcast_json, post_broadcast_schema)
        _check_broadcast_complexity(broadcast_json)
        _validate_template(broadcast_json)

        polygons = Polygons(
            list(
                chain.from_iterable(
                    ([[[y, x] for x, y in polygon] for polygon in area["polygons"]] for area in broadcast_json["areas"])
                )
            )
        )

        if len(polygons) > 12 or polygons.point_count > 250:
            current_app.logger.info(
                "High polygon complexity (%d polygons / %d points ), simplifying...",
                len(polygons),
                polygons.point_count,
            )
            simple_polygons = polygons.smooth.simplify
        else:
            simple_polygons = polygons

        _validate_polygons(simple_polygons.polygons)

        current_app.logger.info(
            "Polygon complexity (%d polygons / %d points)", len(simple_polygons), simple_polygons.point_count
        )

        broadcast_message = BroadcastMessage(
            service_id=authenticated_service.id,
            content=broadcast_json["content"],
            reference=broadcast_json["reference"],
            cap_event=broadcast_json["cap_event"],
            areas={
                "names": [area["name"] for area in broadcast_json["areas"]],
                "simple_polygons": simple_polygons.as_coordinate_pairs_lat_long,
            },
            status=BroadcastStatusType.PENDING_APPROVAL,
            created_by_api_key_id=api_user.id,
            stubbed=authenticated_service.restricted or api_user.key_type == KEY_TYPE_TEST,
            # The client may pass in broadcast_json['expires'] but it’s
            # simpler for now to ignore it and have the rules around expiry
            # for broadcasts created with the API match those created from
            # the admin app
        )

        current_app.logger.info(f"Saving new BroadcastMessage to database: {broadcast_message.serialize()}")

        dao_save_object(broadcast_message)

        current_app.logger.info(
            f"Broadcast message {broadcast_message.id} created for service "
            f"{authenticated_service.id} with reference {broadcast_json['reference']}"
        )

        return jsonify(broadcast_message.serialize()), 201


@v2_broadcast_blueprint.route("", methods=["OPTIONS"])
def return_status():
    response = make_response()
    response.headers["Allow"] = "OPTIONS, POST"
    response.headers["Content-Type"] = "application/json"
    response.status_code = 200
    return response


def _cancel_or_reject_broadcast(references_to_original_broadcast, service_id):
    try:
        broadcast_message = dao_get_broadcast_message_by_references_and_service_id(
            references_to_original_broadcast, service_id
        )
    except MultipleResultsFound:
        raise BadRequestError(
            message="Multiple alerts found - unclear which one to cancel. "
            "Ensure references uniquely identify a single alert.",
            status_code=400,
        )

    if api_user.key_type == KEY_TYPE_TEST and not broadcast_message.stubbed:
        raise AuthError("Cannot cancel a live broadcast with a test API key", 403)

    if broadcast_message.status == BroadcastStatusType.PENDING_APPROVAL:
        new_status = BroadcastStatusType.REJECTED
    else:
        new_status = BroadcastStatusType.CANCELLED
    broadcast_utils.update_broadcast_message_status(broadcast_message, new_status, api_key_id=api_user.id)
    return broadcast_message


def _check_broadcast_complexity(broadcast_json):
    """
    Reject excessively large polygons before Shapely/pyproj processing.
    The 12-polygon / 250-point check in create_broadcast only triggers
    simplification. Without this check, an authenticated broadcast key
    could submit thousands of disjoint unmergeable polygons or a single
    polygon with a huge point count and exhaust API worker CPU/memory.
    """
    polygon_count = 0
    point_count = 0
    for area in broadcast_json["areas"]:
        for polygon in area["polygons"]:
            polygon_count += 1
            point_count += len(polygon)

    max_polygons = current_app.config["MAX_BROADCAST_POLYGON_COUNT"]
    max_points = current_app.config["MAX_BROADCAST_POLYGON_POINT_COUNT"]

    if polygon_count > max_polygons:
        raise BadRequestError(
            message=f"Too many polygons ({polygon_count}); the maximum is {max_polygons}",
            status_code=400,
        )

    if point_count > max_points:
        raise BadRequestError(
            message=f"Too many coordinates ({point_count}); the maximum is {max_points}",
            status_code=400,
        )


def _validate_template(broadcast_json):
    template = BroadcastMessageTemplate.from_content(broadcast_json["content"])

    if template.content_too_long:
        raise ValidationError(
            message=(f"description must be {template.max_content_count:,.0f} " f"characters or fewer")
            + (" (because it could not be GSM7 encoded)" if template.non_gsm_characters else ""),
            status_code=400,
        )


def _check_service_has_permission(type, permissions):
    if type not in permissions:
        raise BadRequestError(message="Service is not allowed to send broadcast messages")


def _check_key_type_allowed(key_type):
    # Team keys are a legacy Notify grouping of 'team & guest list', so they are not
    # allowed to create, cancel or reject alerts. Test keys are allowed but their
    # broadcasts are forced to be stubbed (see create_broadcast / _cancel_or_reject_broadcast).
    if key_type == KEY_TYPE_TEAM:
        raise AuthError("Cannot send broadcasts with a team API key", 403)


def _validate_polygons(polygons):
    try:
        # Build each Shapely polygon exactly once rather than reconstructing both
        # operands on every pass of the nested loop below. The polygon count is
        # bounded up front by _check_broadcast_complexity.
        shapely_polygons = [
            polygon if isinstance(polygon, ShapelyPolygon) else ShapelyPolygon(polygon) for polygon in polygons
        ]

        # Check for overlapping polygons, including partial intersections and
        # enclosed polygons (holes). intersects() is symmetric, so only compare
        # each unordered pair once.
        for p1, p2 in combinations(shapely_polygons, 2):
            if p1.intersects(p2):
                raise ValidationError(
                    message="Overlapping areas are not supported.",
                    status_code=400,
                )
        for p in shapely_polygons:
            # Check if valid (no self-intersections, no duplicate vertices,
            # minimum vertex count, no overlapping segments)
            if not p.is_valid:
                raise ValidationError(
                    message=f"Invalid polygon: {explain_validity(p)}",
                    status_code=400,
                )

    except Exception as e:
        raise ValidationError(
            message=f"Invalid polygon(s): {str(e)}",
            status_code=400,
        ) from e

    return True
