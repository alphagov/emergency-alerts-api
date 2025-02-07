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


def dao_get_latest_broadcast_message_version_number_by_id_and_service_id(
    broadcast_message_id, service_id, version=None
):
    if version is not None:
        return BroadcastMessageHistory.query.filter_by(
            id=broadcast_message_id, service_id=service_id, version=version
        ).one()
    return BroadcastMessageHistory.query.filter_by(id=broadcast_message_id, service_id=service_id).one()


def dao_get_latest_broadcast_message_version_by_id_and_service_id(broadcast_message_id, service_id):
    return (
        BroadcastMessageHistory.query.filter_by(id=broadcast_message_id, service_id=service_id)
        .order_by(desc(BroadcastMessageHistory.version))
        .first()
        .version
    ) or 0


def get_latest_broadcast_message_draft(broadcast_message_id, service_id):
    return (
        BroadcastMessageHistory.query.filter_by(id=broadcast_message_id, service_id=service_id)
        .order_by(desc(BroadcastMessageHistory.version))
        .first()
    )


@autocommit
def dao_create_broadcast_message_version(broadcast_message, service_id):
    latest_version = dao_get_latest_broadcast_message_version_by_id_and_service_id(broadcast_message.id, service_id)
    latest_broadcast_message = get_latest_broadcast_message_draft(broadcast_message.id, service_id)
    if (latest_broadcast_message.reference, latest_broadcast_message.content, latest_broadcast_message.areas) != (
        broadcast_message.reference,
        broadcast_message.content,
        broadcast_message.areas,
    ):
        history = BroadcastMessageHistory(
            **{
                "id": broadcast_message.id,
                "reference": broadcast_message.reference,
                "created_at": broadcast_message.created_at,
                "updated_at": broadcast_message.updated_at,
                "content": broadcast_message.content,
                "service_id": broadcast_message.service_id,
                "created_by_id": broadcast_message.created_by_id,
                "version": latest_version + 1,
                "areas": broadcast_message.areas,
            }
        )
        db.session.add(history)
