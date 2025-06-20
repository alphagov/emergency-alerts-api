import uuid
from datetime import datetime, timezone

from sqlalchemy import asc, desc
from sqlalchemy.orm import aliased

from app import db
from app.dao.dao_utils import autocommit
from app.models import BroadcastMessageEditReasons, User


def dao_get_broadcast_message_edit_reasons(service_id, broadcast_message_id):
    """
    This function retrieves all of the edit_reasons for a specific broadcast message i.e.
    the reasons that the broadcast message has been returned to 'returned' status because something
    is incorrect.
    """
    UserCreated = aliased(User)
    UserSubmitted = aliased(User)
    return (
        db.session.query(
            BroadcastMessageEditReasons, UserCreated.name.label("created_by"), UserSubmitted.name.label("submitted_by")
        )
        .filter_by(service_id=service_id, broadcast_message_id=broadcast_message_id)
        .outerjoin(UserCreated, BroadcastMessageEditReasons.created_by_id == UserCreated.id)
        .outerjoin(UserSubmitted, BroadcastMessageEditReasons.submitted_by_id == UserSubmitted.id)
        .order_by(asc(BroadcastMessageEditReasons.created_at))
        .all()
    )


def dao_get_broadcast_message_edit_reason_by_id(id):
    """
    This function retrieves a specific edit_reason from broadcast_message_edit_reasons table.
    """
    return BroadcastMessageEditReasons.query.filter_by(id=id).one()


def dao_get_latest_broadcast_message_edit_reason_by_broadcast_message_id_and_service_id(
    broadcast_message_id, service_id
):
    """
    This function retrieves the latest edit_reason from broadcast_message_edit_reasons table
    for a specified broadcast message.
    """
    return (
        BroadcastMessageEditReasons.query.filter_by(broadcast_message_id=broadcast_message_id, service_id=service_id)
        .order_by(desc(BroadcastMessageEditReasons.created_at))
        .first()
    )


@autocommit
def dao_create_broadcast_message_edit_reason(broadcast_message, service_id, user_id, edit_reason):
    """This function creates an edit_reason records for broadcast_message_edit_reasons table."""
    history = BroadcastMessageEditReasons(
        **{
            "id": uuid.uuid4(),
            "broadcast_message_id": broadcast_message.id,
            "created_at": datetime.now(timezone.utc),
            "service_id": service_id,
            "created_by_id": user_id,
            "edit_reason": edit_reason,
            "submitted_by_id": broadcast_message.submitted_by_id,
            "submitted_at": broadcast_message.submitted_at,
        }
    )
    db.session.add(history)
    return history
