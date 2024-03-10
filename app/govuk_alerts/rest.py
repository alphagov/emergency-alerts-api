from feedwerk.atom import AtomFeed
from flask import Blueprint, current_app, jsonify

from app.dao.broadcast_message_dao import dao_get_all_broadcast_messages
from app.errors import register_errors
from app.utils import get_dt_string_or_none

govuk_alerts_blueprint = Blueprint("govuk-alerts", __name__)

register_errors(govuk_alerts_blueprint)


@govuk_alerts_blueprint.route("/govuk-alerts")
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


@govuk_alerts_blueprint.route("/govuk-atom")
def get_atom_feed():
    # broadcasts = dao_get_all_broadcast_messages(["broadcasting"])
    broadcasts = dao_get_all_broadcast_messages()

    url = current_app.config["ADMIN_EXTERNAL_URL"]
    feed_url = url + "/alerts.atom"

    feed = AtomFeed(title="Emergency Alerts", feed_url=feed_url, url=url)

    for broadcast in broadcasts:
        feed.add(
            broadcast.reference,
            broadcast.content,
            content_type="html",
            author="GOV.UK",
            url="https://www.gov.uk/alerts/current-alerts",
            published=broadcast.approved_at,
            updated=broadcast.starts_at,
        )

    # return feed.get_response(), 200
    return feed.get_response(), 200
