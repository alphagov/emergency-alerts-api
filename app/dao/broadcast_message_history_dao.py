from sqlalchemy import desc
from sqlalchemy.orm import aliased

from app import db
from app.dao.dao_utils import autocommit
from app.models import BroadcastMessageHistory, User


def dao_get_broadcast_message_versions(service_id, broadcast_message_id):
    UserCreated = aliased(User)
    return (
        db.session.query(BroadcastMessageHistory, UserCreated.name.label("created_by"))
        .filter_by(service_id=service_id, id=broadcast_message_id)
        .outerjoin(UserCreated, BroadcastMessageHistory.created_by_id == UserCreated.id)
        .order_by(desc(BroadcastMessageHistory.version))
        .all()
    )


def dao_get_broadcast_message_by_id_service_id_and_version_number(broadcast_message_id, service_id, version):
    return BroadcastMessageHistory.query.filter_by(
        id=broadcast_message_id, service_id=service_id, version=version
    ).one()


def dao_get_latest_broadcast_message_version_by_id_and_service_id(broadcast_message_id, service_id):
    return (
        BroadcastMessageHistory.query.filter_by(id=broadcast_message_id, service_id=service_id)
        .order_by(desc(BroadcastMessageHistory.version))
        .first()
    )


@autocommit
def dao_create_broadcast_message_version(broadcast_message, service_id, user_id=None):
    """
    This function gets latest version of broadcast message from broadcast_message_history, if there is one,
    compares changes with broadcast_message input (where possible), creates a version using the broadcast_message
    attributes and increments version number by 1.
    """
    latest_broadcast_message = dao_get_latest_broadcast_message_version_by_id_and_service_id(
        broadcast_message.id, service_id
    )
    latest_version = latest_broadcast_message.version if latest_broadcast_message else 0
    updating_user = broadcast_message.created_by if latest_version is None else user_id
    history = None
    if latest_broadcast_message is None:
        history = BroadcastMessageHistory(
            **{
                "id": broadcast_message.id,
                "reference": broadcast_message.reference,
                "created_at": broadcast_message.created_at,
                "content": broadcast_message.content,
                "service_id": broadcast_message.service_id,
                "created_by_id": updating_user,
                "version": 1,
                "areas": broadcast_message.areas or None,
            }
        )
    elif (
        latest_broadcast_message.reference,
        latest_broadcast_message.content,
        latest_broadcast_message.areas,
    ) != (
        broadcast_message.reference,
        broadcast_message.content,
        broadcast_message.areas,
    ):
        # If any attributes have changed, new version created
        history = BroadcastMessageHistory(
            **{
                "id": broadcast_message.id,
                "reference": broadcast_message.reference or latest_broadcast_message.reference,
                "created_at": broadcast_message.created_at,
                "content": broadcast_message.content or latest_broadcast_message.content,
                "service_id": broadcast_message.service_id,
                "created_by_id": updating_user,
                "version": latest_version + 1,
                "areas": broadcast_message.areas or latest_broadcast_message.areas,
            }
        )
    if history:
        db.session.add(history)
