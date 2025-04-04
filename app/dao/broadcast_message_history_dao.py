import uuid
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import aliased

from app import db
from app.dao.dao_utils import autocommit
from app.models import BroadcastMessageHistory, User


def dao_get_broadcast_message_versions(service_id, broadcast_message_id):
    UserCreated = aliased(User)
    return (
        db.session.query(BroadcastMessageHistory, UserCreated.name.label("created_by"))
        .filter_by(service_id=service_id, broadcast_message_id=broadcast_message_id)
        .outerjoin(UserCreated, BroadcastMessageHistory.created_by_id == UserCreated.id)
        .order_by(desc(BroadcastMessageHistory.created_at))
        .all()
    )


def dao_get_broadcast_message_version_by_id(id):
    return BroadcastMessageHistory.query.filter_by(id=id).one()


def dao_get_latest_broadcast_message_version_bybroadcast_message_id_and_service_id(broadcast_message_id, service_id):
    return (
        BroadcastMessageHistory.query.filter_by(broadcast_message_id=broadcast_message_id, service_id=service_id)
        .order_by(desc(BroadcastMessageHistory.created_at))
        .first()
    )


@autocommit
def dao_create_broadcast_message_version(broadcast_message, service_id, user_id=None):
    """
    This function gets latest version of broadcast message from broadcast_message_history, if there is one,
    compares changes with broadcast_message input (where possible), creates a version using the broadcast_message
    attributes.
    """
    latest_broadcast_message = dao_get_latest_broadcast_message_version_bybroadcast_message_id_and_service_id(
        broadcast_message.id, service_id
    )

    updating_user = None

    if user_id is not None:
        updating_user = user_id
    elif latest_broadcast_message is None:
        updating_user = broadcast_message.created_by_id

    history = None
    if latest_broadcast_message is None:
        history = BroadcastMessageHistory(
            **{
                "id": uuid.uuid4(),
                "broadcast_message_id": broadcast_message.id,
                "reference": broadcast_message.reference,
                "created_at": datetime.now(timezone.utc),
                "content": broadcast_message.content,
                "service_id": broadcast_message.service_id,
                "created_by_id": updating_user,
                "areas": broadcast_message.areas or None,
                "duration": broadcast_message.duration,
            }
        )
    elif (
        latest_broadcast_message.reference,
        latest_broadcast_message.content,
        latest_broadcast_message.areas,
        latest_broadcast_message.duration,
    ) != (broadcast_message.reference, broadcast_message.content, broadcast_message.areas, broadcast_message.duration):
        # If any attributes have changed, new version created
        history = BroadcastMessageHistory(
            **{
                "id": uuid.uuid4(),
                "broadcast_message_id": broadcast_message.id,
                "reference": broadcast_message.reference or latest_broadcast_message.reference,
                "created_at": datetime.now(timezone.utc),
                "content": broadcast_message.content or latest_broadcast_message.content,
                "service_id": broadcast_message.service_id,
                "created_by_id": updating_user,
                "areas": broadcast_message.areas or latest_broadcast_message.areas,
                "duration": broadcast_message.duration or latest_broadcast_message.duration,
            }
        )
    if history:
        db.session.add(history)
