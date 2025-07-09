from flask import Blueprint, current_app, jsonify

from app.dao.broadcast_message_dao import (
    dao_get_all_broadcast_messages,
    dao_mark_all_as_govuk_acknowledged,
)
from app.errors import register_errors
from app.utils import get_dt_string_or_none

govuk_alerts_blueprint = Blueprint(
    "govuk-alerts",
    __name__,
    url_prefix="/govuk-alerts",
)

register_errors(govuk_alerts_blueprint)


@govuk_alerts_blueprint.route("")
def get_broadcasts():
    broadcasts = dao_get_all_broadcast_messages()
    broadcasts_dict = {
        "alerts": [
            {
                "id": broadcast.id,
                "reference": broadcast.reference,
                "channel": broadcast.channel,
                "content": broadcast.content,
                "areas": broadcast.areas,
                "status": broadcast.status,
                "starts_at": get_dt_string_or_none(broadcast.starts_at),
                "finishes_at": get_dt_string_or_none(broadcast.finishes_at),
                "approved_at": get_dt_string_or_none(broadcast.approved_at),
                "cancelled_at": get_dt_string_or_none(broadcast.cancelled_at),
            }
            for broadcast in broadcasts
        ]
    }
    return jsonify(broadcasts_dict), 200


@govuk_alerts_blueprint.route("/acknowledge", methods=["POST"])
def acknowledge_finished_broadcasts():
    """Called by GovUK after it has finished publishing. We mark any finished BroadcastMessages as having completed"""
    marked_done = dao_mark_all_as_govuk_acknowledged()

    current_app.logger.info(f"GovUK has finished publishing. Marked {len(marked_done)} records as acknowledged")

    return {}, 200
