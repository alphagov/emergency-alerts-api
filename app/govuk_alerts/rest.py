from flask import Blueprint, current_app, jsonify

from app.dao.broadcast_message_dao import (
    dao_get_all_broadcast_messages,
    dao_get_filtered_broadcast_messages,
    dao_mark_all_as_govuk_acknowledged,
)
from app.errors import register_errors
from app.schema_validation import validate
from app.schema_validation.definitions import live_broadcast_areas
from app.utils import get_dt_string_or_none

govuk_alerts_blueprint = Blueprint(
    "govuk-alerts",
    __name__,
    url_prefix="/govuk-alerts",
)

register_errors(govuk_alerts_blueprint)


@govuk_alerts_blueprint.route("")
def get_broadcasts():
    broadcasts = dao_get_filtered_broadcast_messages()
    return jsonify({"alerts": _serialise_broadcasts(broadcasts, include_updated_at=True)}), 200


@govuk_alerts_blueprint.route("/all")
def get_all_broadcasts():
    broadcasts = dao_get_all_broadcast_messages()
    return jsonify({"alerts": _serialise_broadcasts(broadcasts, include_updated_at=False)}), 200


def _serialise_broadcasts(broadcasts, *, include_updated_at):
    """
    One malformed alert would otherwise fail publishing of every alert, so any alert that doesn't
    match the schema, or can't be serialised, is logged and left out.
    """
    alerts = []
    for broadcast in broadcasts:
        try:
            validate(broadcast.areas, live_broadcast_areas)
            alert = {
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
                "extra_content": broadcast.extra_content,
            }
            if include_updated_at:
                alert["updated_at"] = get_dt_string_or_none(broadcast.updated_at)
        except Exception:
            current_app.logger.exception(
                "Skipping broadcast message that cannot be published to gov.uk/alerts",
                extra={"python_module": __name__, "broadcast_message_id": broadcast.id},
            )
            continue
        alerts.append(alert)
    return alerts


@govuk_alerts_blueprint.route("/acknowledge", methods=["POST"])
def acknowledge_finished_broadcasts():
    """Called by GovUK after it has finished publishing. We mark any finished BroadcastMessages as having completed"""
    marked_done = dao_mark_all_as_govuk_acknowledged()

    current_app.logger.info(f"GovUK has finished publishing. Marked {len(marked_done)} records as acknowledged")

    return {}, 200
