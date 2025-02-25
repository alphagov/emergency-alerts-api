from datetime import datetime, timezone

from emergency_alerts_utils.admin_action import (
    ADMIN_EDIT_PERMISSIONS,
    ADMIN_STATUS_PENDING,
)
from flask import Blueprint, jsonify, request

from app.admin_action.admin_action_schema import (
    create_admin_action_schema,
    review_admin_action_schema,
)
from app.dao.admin_action_dao import (
    dao_get_admin_action_by_id,
    dao_get_pending_admin_actions,
)
from app.dao.dao_utils import dao_save_object
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.users_dao import get_user_by_id
from app.models import AdminAction
from app.schema_validation import validate

admin_action_blueprint = Blueprint("admin_action", __name__)


@admin_action_blueprint.route("", methods=["POST"])
def create_admin_action():
    data = request.get_json()

    validate(data, create_admin_action_schema)

    admin_action = AdminAction(
        service_id=data["service_id"],
        action_type=data["action_type"],
        action_data=data["action_data"],
        created_by_id=data["created_by"],
        status=ADMIN_STATUS_PENDING,
    )

    dao_save_object(admin_action)

    # TODO; Assert there isn't already an approval for the same action?

    return jsonify(admin_action.serialize()), 201


@admin_action_blueprint.route("/pending", methods=["GET"])
def get_pending_admin_actions():
    pending = [x.serialize() for x in dao_get_pending_admin_actions()]

    # Grab related data to show in the UI:
    service_ids = set(x["service_id"] for x in pending)
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
