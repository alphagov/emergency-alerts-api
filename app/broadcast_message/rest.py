import iso8601
from emergency_alerts_utils.template import BroadcastMessageTemplate
from flask import Blueprint, current_app, jsonify, request

from app.broadcast_message import utils as broadcast_utils
from app.broadcast_message.broadcast_message_schema import (
    create_broadcast_message_schema,
    update_broadcast_message_schema,
    update_broadcast_message_status_schema,
)
from app.broadcast_message_history.rest import create_broadcast_message_version
from app.dao.broadcast_message_dao import (
    dao_get_broadcast_message_by_id_and_service_id,
    dao_get_broadcast_message_by_id_and_service_id_with_user,
    dao_get_broadcast_messages_for_service,
    dao_get_broadcast_messages_for_service_with_user,
    dao_get_broadcast_provider_messages_by_broadcast_message_id,
    dao_purge_old_broadcast_messages,
)
from app.dao.dao_utils import dao_save_object
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest, register_errors
from app.models import BroadcastMessage, BroadcastStatusType
from app.schema_validation import validate
from app.utils import is_public_environment

broadcast_message_blueprint = Blueprint(
    "broadcast_message", __name__, url_prefix="/service/<uuid:service_id>/broadcast-message"
)
register_errors(broadcast_message_blueprint)


def _parse_nullable_datetime(dt):
    if dt:
        return iso8601.parse_date(dt).replace(tzinfo=None)
    return dt


@broadcast_message_blueprint.route("", methods=["GET"])
def get_broadcast_messages_for_service(service_id):
    # TODO: should this return template content/data in some way? or can we rely on them being cached admin side.
    # we might need stuff like template name for showing on the dashboard.
    # TODO: should this paginate or filter on dates or anything?
    broadcast_messages = [o.serialize() for o in dao_get_broadcast_messages_for_service(service_id)]
    return jsonify(broadcast_messages=broadcast_messages)


@broadcast_message_blueprint.route("/<uuid:broadcast_message_id>", methods=["GET"])
def get_broadcast_message(service_id, broadcast_message_id):
    return jsonify(dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id).serialize())


@broadcast_message_blueprint.route("/messages", methods=["GET"])
def get_broadcast_msgs_for_service(service_id):
    broadcast_messages = [
        {
            **message.serialize(),
            "created_by": creatd_by or None,
            "rejected_by": rejectd_by or None,
            "approved_by": approvd_by or None,
            "cancelled_by": cancelld_by or None,
        }
        for message, creatd_by, rejectd_by, approvd_by, cancelld_by in dao_get_broadcast_messages_for_service_with_user(
            service_id
        )
    ]
    return jsonify(broadcast_messages=broadcast_messages)


@broadcast_message_blueprint.route("/message=<uuid:broadcast_message_id>", methods=["GET"])
def get_broadcast_message_by_id_and_service(service_id, broadcast_message_id):
    result = dao_get_broadcast_message_by_id_and_service_id_with_user(broadcast_message_id, service_id)
    return {
        **result[0].serialize(),
        "created_by": result[1] or None,
        "rejected_by": result[2] or None,
        "approved_by": result[3] or None,
        "cancelled_by": result[4] or None,
    }


@broadcast_message_blueprint.route("/<uuid:broadcast_message_id>/provider-messages", methods=["GET"])
def get_broadcast_provider_messages(service_id, broadcast_message_id):
    messages = dao_get_broadcast_provider_messages_by_broadcast_message_id(broadcast_message_id)

    messages_dict = {
        "messages": [
            {
                "id": message.id,
                "provider": message.provider,
                "status": message.status,
            }
            for message in messages
        ]
    }

    return jsonify(messages_dict)


@broadcast_message_blueprint.route("", methods=["POST"])
def create_broadcast_message(service_id):
    data = request.get_json()

    validate(data, create_broadcast_message_schema)
    service = dao_fetch_service_by_id(data["service_id"])
    user = get_user_by_id(data["created_by"])
    template_id = data.get("template_id")

    if template_id:
        template = dao_get_template_by_id_and_service_id(template_id, data["service_id"])
        content = str(template._as_utils_template())
        reference = str(template.name)
    else:
        temporary_template = BroadcastMessageTemplate.from_content(data["content"])
        if temporary_template.content_too_long:
            raise InvalidRequest(
                (f"Content must be " f"{temporary_template.max_content_count:,.0f} " f"characters or fewer")
                + (" (because it could not be GSM7 encoded)" if temporary_template.non_gsm_characters else ""),
                status_code=400,
            )
        template = None
        content = str(temporary_template)
        reference = data["reference"]

    broadcast_message = BroadcastMessage(
        service_id=service.id,
        template_id=template_id,
        template_version=template.version if template else None,
        areas=data.get("areas", {}),
        status=BroadcastStatusType.DRAFT,
        starts_at=_parse_nullable_datetime(data.get("starts_at")),
        finishes_at=_parse_nullable_datetime(data.get("finishes_at")),
        created_by_id=user.id,
        content=content,
        reference=reference,
        stubbed=service.restricted,
    )

    dao_save_object(broadcast_message)
    create_broadcast_message_version(broadcast_message, service_id, user.id)

    return jsonify(broadcast_message.serialize()), 201


@broadcast_message_blueprint.route("/<uuid:broadcast_message_id>", methods=["POST"])
def update_broadcast_message(service_id, broadcast_message_id):
    data = request.get_json()
    updating_user = data.get("created_by") or None
    validate(data, update_broadcast_message_schema)

    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id)

    if broadcast_message.status not in BroadcastStatusType.PRE_BROADCAST_STATUSES:
        raise InvalidRequest(
            f"Cannot update broadcast_message {broadcast_message.id} while it has status {broadcast_message.status}",
            status_code=400,
        )

    areas = data.get("areas", {})

    if ("ids" in areas and "simple_polygons" not in areas) or ("ids" not in areas and "simple_polygons" in areas):
        raise InvalidRequest(
            f"Cannot update broadcast_message {broadcast_message.id}, area IDs or polygons are missing.",
            status_code=400,
        )

    if "personalisation" in data:
        broadcast_message.personalisation = data["personalisation"]
    if "reference" in data:
        broadcast_message.reference = data["reference"]
    if "content" in data:
        broadcast_message.content = data["content"]
    if "duration" in data:
        broadcast_message.duration = data["duration"]
    if "starts_at" in data:
        broadcast_message.starts_at = _parse_nullable_datetime(data["starts_at"])
    if "finishes_at" in data:
        broadcast_message.finishes_at = _parse_nullable_datetime(data["finishes_at"])
    if "ids" in areas and "simple_polygons" in areas:
        broadcast_message.areas = areas

    dao_save_object(broadcast_message)
    create_broadcast_message_version(broadcast_message, service_id, updating_user)

    return jsonify(broadcast_message.serialize()), 200


@broadcast_message_blueprint.route("/<uuid:broadcast_message_id>/status", methods=["POST"])
def update_broadcast_message_status(service_id, broadcast_message_id):
    data = request.get_json()
    validate(data, update_broadcast_message_status_schema)
    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id)
    current_app.logger.info(
        "update_broadcast_message_status",
        extra={
            "python_module": __name__,
            "service_id": service_id,
            "broadcast_message_id": broadcast_message_id,
            "status": data["status"],
        },
    )
    if not broadcast_message.service.active:
        raise InvalidRequest("Updating broadcast message is not allowed: service is inactive ", 403)

    new_status = data["status"]
    updating_user = get_user_by_id(data["created_by"])

    if updating_user not in broadcast_message.service.users:
        #  we allow platform admins to cancel broadcasts, and we don't check user if request was done via API
        if not (new_status == BroadcastStatusType.CANCELLED and updating_user.platform_admin):
            raise InvalidRequest(
                f"User {updating_user.id} cannot update broadcast_message {broadcast_message.id} from other service",
                status_code=400,
            )

    broadcast_utils.update_broadcast_message_status(broadcast_message, new_status, updating_user)
    return jsonify(broadcast_message.serialize()), 200


@broadcast_message_blueprint.route("/<uuid:broadcast_message_id>/check-status", methods=["POST"])
def check_user_can_update_broadcast_message_status(service_id, broadcast_message_id):
    data = request.get_json()
    validate(data, update_broadcast_message_status_schema)
    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id)

    new_status = data["status"]
    updating_user = get_user_by_id(data["created_by"])

    try:
        broadcast_utils._validate_broadcast_update(broadcast_message, new_status, updating_user)
    except InvalidRequest as e:
        if new_status in BroadcastStatusType.ALLOWED_STATUS_TRANSITIONS[broadcast_message.status]:
            raise e  # Raising any other InvalidRequest that has been raised

        if broadcast_message.status == "pending-approval":
            raise InvalidRequest(
                "This alert is pending approval, it cannot be edited or submitted again.",
                400,
            ) from e
        elif broadcast_message.status == "rejected":
            raise InvalidRequest(
                "This alert has been rejected, it cannot be edited or resubmitted for approval.",
                400,
            ) from e
        elif broadcast_message.status == "broadcasting":
            raise InvalidRequest(
                "This alert is live, it cannot be edited or submitted again.",
                400,
            ) from e
        elif broadcast_message.status in ["cancelled", "completed"]:
            raise InvalidRequest(
                "This alert has already been broadcast, it cannot be edited or resubmitted for approval.",
                400,
            ) from e
    return (
        {},
        200,
    )


@broadcast_message_blueprint.route("/<uuid:broadcast_message_id>/status-with-reason", methods=["POST"])
def update_broadcast_message_status_with_reason(service_id, broadcast_message_id):
    data = request.get_json()

    validate(data, update_broadcast_message_status_schema)
    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id)

    current_app.logger.info(
        "update_broadcast_message_status",
        extra={
            "python_module": __name__,
            "service_id": service_id,
            "broadcast_message_id": broadcast_message_id,
            "status": data["status"],
        },
    )

    if not broadcast_message.service.active:
        raise InvalidRequest("Updating broadcast message is not allowed: service is inactive ", 403)

    new_status = data["status"]
    rejection_reason = data.get("rejection_reason", "")
    if new_status == "rejected" and rejection_reason == "":
        return (
            jsonify({"errors": ["Enter the reason for rejecting the alert."]}),
            400,
        )
    updating_user = get_user_by_id(data["created_by"])

    if updating_user not in broadcast_message.service.users:
        #  we allow platform admins to cancel broadcasts, and we don't check user if request was done via API
        if not (new_status == BroadcastStatusType.CANCELLED and updating_user.platform_admin):
            raise InvalidRequest(
                f"User {updating_user.id} cannot update broadcast_message {broadcast_message.id} from other service",
                status_code=400,
            )

    broadcast_utils.update_broadcast_message_status(
        broadcast_message, new_status, updating_user, rejection_reason=rejection_reason or None
    )

    return jsonify(broadcast_message.serialize()), 200


@broadcast_message_blueprint.route("/purge/<int:older_than>", methods=["DELETE"])
def purge_broadcast_messages(service_id, older_than):
    if is_public_environment():
        raise InvalidRequest("Endpoint not found", status_code=404)

    try:
        count = dao_purge_old_broadcast_messages(service=service_id, days_older_than=older_than)
    except Exception as e:
        return jsonify(result="error", message=f"Unable to purge old alert items: {e}"), 500

    return (
        jsonify(
            {
                "message": f"Purged {count['msgs']} BroadcastMessage items and {count['events']} "
                f"BroadcastEvent items, created more than {older_than} days ago"
            }
        ),
        200,
    )
