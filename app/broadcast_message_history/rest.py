from flask import Blueprint, jsonify

from app.dao.broadcast_message_history_dao import (
    dao_get_broadcast_message_version_by_id,
    dao_get_broadcast_message_versions,
)
from app.errors import register_errors
from app.schemas import broadcast_message_history_schema

broadcast_message_history_blueprint = Blueprint(
    "broadcast_message_history", __name__, url_prefix="/service/<uuid:service_id>/broadcast-message-history"
)
register_errors(broadcast_message_history_blueprint)


@broadcast_message_history_blueprint.route("/<uuid:broadcast_message_id>/version/<uuid:id>")
def get_broadcast_message_version_by_id(service_id, broadcast_message_id, id):
    data = broadcast_message_history_schema.dump(dao_get_broadcast_message_version_by_id(id))
    return jsonify(data)


@broadcast_message_history_blueprint.route("/<uuid:broadcast_message_id>/versions")
def get_broadcast_message_versions(service_id, broadcast_message_id):
    broadcast_messages = []
    for message, created_by in dao_get_broadcast_message_versions(
        service_id=service_id, broadcast_message_id=broadcast_message_id
    ):
        broadcast_messages.append(
            {
                **message.serialize(),
                "created_by": created_by or None,
            }
        )

    return jsonify(broadcast_messages)
