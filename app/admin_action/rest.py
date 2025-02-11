from datetime import datetime, timezone

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
from app.dao.organisation_dao import dao_get_organisation_by_id
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest
from app.models import ADMIN_STATUS_PENDING, AdminAction
from app.schema_validation import validate

admin_action_blueprint = Blueprint("admin_action", __name__)


@admin_action_blueprint.route("", methods=["POST"])
def create_admin_action():
    data = request.get_json()

    validate(data, create_admin_action_schema)

    admin_action = AdminAction(
        organisation_id=data["organisation_id"],
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
    organisation_ids = set(x["organization_id"] for x in pending)
    service_ids = set(x["service_id"] for x in pending)
    user_ids = set(x["created_by"] for x in pending)

    organizations = dict((str(x), dao_get_organisation_by_id(x).serialize_for_list()) for x in organisation_ids)
    services = dict((str(x), dao_fetch_service_by_id(x).serialize_for_org_dashboard()) for x in service_ids)
    users = dict((str(x), get_user_by_id(x).serialize_for_users_list()) for x in user_ids)

    ret = {
        "pending": pending,
        "organizations": organizations,
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
        raise InvalidRequest("Action is not pending", status_code=400)

    admin_action.reviewed_at = datetime.now(timezone.utc)
    admin_action.reviewed_by_id = data["reviewed_by"]
    admin_action.status = data["status"]

    dao_save_object(admin_action)

    return jsonify(admin_action.serialize()), 200
