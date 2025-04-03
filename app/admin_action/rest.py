from datetime import datetime, timezone

from emergency_alerts_utils.admin_action import (
    ADMIN_CREATE_API_KEY,
    ADMIN_EDIT_PERMISSIONS,
    ADMIN_ELEVATE_USER,
    ADMIN_INVITE_USER,
    ADMIN_STATUS_PENDING,
)
from flask import Blueprint, abort, current_app, jsonify, request

from app.admin_action.admin_action_schema import (
    create_admin_action_schema,
    review_admin_action_schema,
)
from app.dao.admin_action_dao import (
    dao_delete_admin_action_by_id,
    dao_get_admin_action_by_id,
    dao_get_all_admin_actions_by_user_id,
    dao_get_pending_valid_admin_actions,
)
from app.dao.dao_utils import dao_save_object
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest
from app.models import AdminAction
from app.schema_validation import validate
from app.utils import is_public_environment

admin_action_blueprint = Blueprint("admin_action", __name__)


@admin_action_blueprint.route("", methods=["POST"])
def create_admin_action():
    data = request.get_json()

    validate(data, create_admin_action_schema)

    pending = dao_get_pending_valid_admin_actions()
    for pending_action in pending:
        if _admin_action_is_similar(pending_action.serialize(), data):
            current_app.logger.error(
                f"409 Conflict: Requested to create AdminAction {data}, "
                + f"but this was similar to existing one: {pending_action}.",
                extra={"python_module": __name__},
            )
            return abort(409)  # Conflict

    admin_action = AdminAction(
        service_id=data.get("service_id", None),
        action_type=data["action_type"],
        action_data=data["action_data"],
        created_by_id=data["created_by"],
        status=ADMIN_STATUS_PENDING,
    )

    dao_save_object(admin_action)

    # TODO: Slack

    return jsonify(admin_action.serialize()), 201


@admin_action_blueprint.route("/pending", methods=["GET"])
def get_pending_admin_actions():
    pending = [x.serialize() for x in dao_get_pending_valid_admin_actions()]

    # Grab related data to show in the UI:
    service_ids = set(x["service_id"] for x in pending)
    service_ids.discard(None)  # service_id can be optional for some admin actions
    user_ids = set(x["created_by"] for x in pending)

    for action in pending:
        # This action contains just a user ID but grab it for related data
        if action["action_type"] == ADMIN_EDIT_PERMISSIONS:
            user_ids.add(action["action_data"]["user_id"])

    services = dict((str(x), dao_fetch_service_by_id(x).serialize_for_org_dashboard()) for x in service_ids)
    users = dict((str(x), get_user_by_id(x).serialize_for_users_list()) for x in user_ids)

    ret = {
        "pending": pending,
        "services": services,
        "users": users,
    }

    return jsonify(ret), 200


@admin_action_blueprint.route("/<uuid:action_id>", methods=["GET"])
def get_admin_action_by_id(action_id):
    action = dao_get_admin_action_by_id(action_id)

    return jsonify(action.serialize()), 200


@admin_action_blueprint.route("/<uuid:action_id>/review", methods=["POST"])
def review_admin_action(action_id):
    data = request.get_json()
    validate(data, review_admin_action_schema)

    admin_action = dao_get_admin_action_by_id(action_id)

    # Is it already approved/rejected?
    if admin_action.status != ADMIN_STATUS_PENDING:
        return (
            jsonify({"errors": ["The action is not pending"]}),
            400,
        )
    admin_action.reviewed_at = datetime.now(timezone.utc)
    admin_action.reviewed_by_id = data["reviewed_by"]
    admin_action.status = data["status"]

    dao_save_object(admin_action)

    return jsonify(admin_action.serialize()), 200


@admin_action_blueprint.route("/purge/<uuid:user_id>", methods=["DELETE"])
def purge_test_admin_actions_created_by(user_id):
    if is_public_environment():
        raise InvalidRequest("Endpoint not found", status_code=404)

    try:
        actions = dao_get_all_admin_actions_by_user_id(user_id)
        for action in actions:
            dao_delete_admin_action_by_id(action.id)
    except Exception as e:
        return jsonify(result="error", message=f"Unable to purge admin actions created by user {user_id}: {e}"), 500

    return jsonify({"message": "Successfully purged admin actions"}), 200


def _admin_action_is_similar(action_obj1, action_obj2):
    """
    Similar being related to the same subject, e.g. inviting the same user to the same service.
    """
    # service_id is optional
    if action_obj1.get("service_id") != action_obj2.get("service_id"):
        return False

    if action_obj1["action_type"] != action_obj2["action_type"]:
        return False

    if action_obj1["action_type"] == ADMIN_INVITE_USER:
        return action_obj1["action_data"]["email_address"] == action_obj2["action_data"]["email_address"]
    elif action_obj1["action_type"] == ADMIN_EDIT_PERMISSIONS:
        return action_obj1["action_data"]["user_id"] == action_obj2["action_data"]["user_id"]
    elif action_obj1["action_type"] == ADMIN_CREATE_API_KEY:
        return action_obj1["action_data"]["key_name"] == action_obj2["action_data"]["key_name"]
    elif action_obj1["action_type"] == ADMIN_ELEVATE_USER:
        return action_obj1["created_by"] == action_obj2["created_by"]
    else:
        raise Exception("The action_type {} is unknown".format(action_obj1["action_type"]))
