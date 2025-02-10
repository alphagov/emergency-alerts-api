from flask import Blueprint, jsonify, request

from app.admin_action.admin_action_schema import create_admin_action_schema
from app.dao.admin_action_dao import dao_get_pending_admin_actions
from app.dao.dao_utils import dao_save_object
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
        created_by=data["created_by"],
        status=ADMIN_STATUS_PENDING,
    )

    dao_save_object(admin_action)

    # TODO; Assert there isn't already an approval for the same action?

    return jsonify(admin_action.serialize()), 201


@admin_action_blueprint.route("/pending", methods=["GET"])
def get_pending_admin_actions():
    pending = [x.serialize() for x in dao_get_pending_admin_actions()]

    return jsonify(pending), 200
