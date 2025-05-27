from flask import Blueprint, jsonify

from app.dao.broadcast_message_edit_reasons import (
    dao_get_broadcast_message_edit_reason_by_id,
    dao_get_broadcast_message_edit_reasons,
    dao_get_latest_broadcast_message_edit_reason_by_broadcast_message_id_and_service_id,
)
from app.errors import register_errors
from app.schemas import broadcast_message_edit_reason_schema

broadcast_message_edit_reasons_blueprint = Blueprint(
    "broadcast_message_edit_reasons", __name__, url_prefix="/service/<uuid:service_id>/broadcast-message-edit-reasons"
)
register_errors(broadcast_message_edit_reasons_blueprint)


@broadcast_message_edit_reasons_blueprint.route("/<uuid:broadcast_message_id>/edit-reason/<uuid:id>")
def get_broadcast_message_edit_reason_by_id(service_id, broadcast_message_id, id):
    data = broadcast_message_edit_reason_schema.dump(dao_get_broadcast_message_edit_reason_by_id(id))
    return jsonify(data)


@broadcast_message_edit_reasons_blueprint.route("/<uuid:broadcast_message_id>/latest-edit-reason")
def get_latest_broadcast_message_edit_reason(service_id, broadcast_message_id):
    data = broadcast_message_edit_reason_schema.dump(
        dao_get_latest_broadcast_message_edit_reason_by_broadcast_message_id_and_service_id(
            broadcast_message_id, service_id
        )
    )
    return jsonify(data)


@broadcast_message_edit_reasons_blueprint.route("/<uuid:broadcast_message_id>/edit-reasons")
def get_broadcast_message_edit_reasons(service_id, broadcast_message_id):
    edit_reasons = []
    for edit_reason, created_by, submitted_by in dao_get_broadcast_message_edit_reasons(
        service_id=service_id, broadcast_message_id=broadcast_message_id
    ):
        edit_reasons.append(
            {**edit_reason.serialize(), "created_by": created_by or None, "submitted_by": submitted_by or None}
        )

    return jsonify(edit_reasons)
