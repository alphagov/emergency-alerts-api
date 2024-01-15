import uuid
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import desc

from app import db
from app.dao.dao_utils import autocommit
from app.models import (
    BroadcastEvent,
    BroadcastMessage,
    BroadcastProvider,
    BroadcastProviderMessage,
    BroadcastProviderMessageNumber,
    BroadcastProviderMessageStatus,
    BroadcastStatusType,
    Service,
    ServiceBroadcastSettings,
)


def dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id):
    return BroadcastMessage.query.filter(
        BroadcastMessage.id == broadcast_message_id, BroadcastMessage.service_id == service_id
    ).one()


def dao_get_broadcast_message_by_references_and_service_id(references_to_original_broadcast, service_id):
    return BroadcastMessage.query.filter(
        BroadcastMessage.status.in_(
            (
                BroadcastStatusType.PENDING_APPROVAL,
                BroadcastStatusType.BROADCASTING,
            )
        ),
        BroadcastMessage.reference.in_(references_to_original_broadcast),
        BroadcastMessage.service_id == service_id,
    ).one()


def dao_get_broadcast_event_by_id(broadcast_event_id):
    return BroadcastEvent.query.filter(BroadcastEvent.id == broadcast_event_id).one()


def dao_get_broadcast_messages_for_service(service_id):
    return BroadcastMessage.query.filter(BroadcastMessage.service_id == service_id).order_by(
        BroadcastMessage.created_at
    )


def dao_get_broadcast_provider_messages_by_broadcast_message_id(broadcast_message_id):
    return (
        db.session.query(
            BroadcastProviderMessage.id,
            BroadcastProviderMessage.provider,
            BroadcastProviderMessage.status,
        )
        .join(BroadcastEvent, BroadcastEvent.id == BroadcastProviderMessage.broadcast_event_id)
        .filter(BroadcastEvent.broadcast_message_id == broadcast_message_id)
        .all()
    )


def dao_get_all_broadcast_messages():
    return (
        db.session.query(
            BroadcastMessage.id,
            BroadcastMessage.reference,
            ServiceBroadcastSettings.channel,
            BroadcastMessage.content,
            BroadcastMessage.areas,
            BroadcastMessage.status,
            BroadcastMessage.starts_at,
            BroadcastMessage.finishes_at,
            BroadcastMessage.approved_at,
            BroadcastMessage.cancelled_at,
        )
        .join(ServiceBroadcastSettings, ServiceBroadcastSettings.service_id == BroadcastMessage.service_id)
        .filter(
            BroadcastMessage.starts_at >= datetime(2021, 5, 25, 0, 0, 0),
            BroadcastMessage.stubbed == False,  # noqa
            BroadcastMessage.status.in_(BroadcastStatusType.LIVE_STATUSES),
        )
        .order_by(desc(BroadcastMessage.starts_at))
        .all()
    )


def dao_purge_old_broadcast_messages(days_older_than=30, service=None):
    service_id = None
    session = db.session
    if service is None:
        service_id = current_app.config["FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID"]
    else:
        try:
            _ = uuid.UUID(service)
            if session.query(Service.name).filter(Service.id == service).one():
                service_id = service
        except ValueError:
            service_id = session.query(Service.id).filter(Service.name == service).one()

    if service_id is None:
        raise "Unable to find service ID"

    print(f"Purging alerts for service {service_id}")

    messages = (
        session.query(
            BroadcastMessage.id,
        )
        .filter(
            BroadcastMessage.service_id == service_id,
            BroadcastMessage.created_at <= datetime.now() - timedelta(days=days_older_than),
            BroadcastMessage.status.in_(BroadcastStatusType.PRE_BROADCAST_STATUSES + BroadcastStatusType.LIVE_STATUSES),
        )
        .all()
    )

    print(f"Messages associated with service {service_id}:")
    print(messages)

    for message in messages:
        try:
            broadcast_event_rows = session.query(BroadcastEvent.id).filter_by(broadcast_message_id=message.id).all()
            broadcast_event_ids = [str(row[0]) for row in broadcast_event_rows]

            print(f"Event IDs associated with message {message.id}: {broadcast_event_ids}")

            broadcast_provider_message_rows = (
                session.query(BroadcastProviderMessage.id)
                .filter(BroadcastProviderMessage.broadcast_event_id.in_(broadcast_event_ids))
                .all()
            )
            broadcast_provider_message_ids = [str(row[0]) for row in broadcast_provider_message_rows]

            print(f"BroadcastProviderMessage rows associated with events: {broadcast_provider_message_ids}")

            session.query(BroadcastProviderMessageNumber).filter(
                BroadcastProviderMessageNumber.broadcast_provider_message_id.in_(broadcast_provider_message_ids)
            ).delete(synchronize_session=False)

            session.query(BroadcastProviderMessage).filter(
                BroadcastProviderMessage.id.in_(broadcast_provider_message_ids)
            ).delete(synchronize_session=False)

            session.query(BroadcastEvent).filter(BroadcastEvent.id.in_(broadcast_event_ids)).delete(
                synchronize_session=False
            )

            session.query(BroadcastMessage).filter_by(id=message.id).delete(synchronize_session=False)

            session.commit()
        except Exception as e:
            session.rollback()
            raise e


def get_earlier_events_for_broadcast_event(broadcast_event_id):
    """
    This is used to build up the references list.
    """
    this_event = BroadcastEvent.query.get(broadcast_event_id)

    return (
        BroadcastEvent.query.filter(
            BroadcastEvent.broadcast_message_id == this_event.broadcast_message_id,
            BroadcastEvent.sent_at < this_event.sent_at,
        )
        .order_by(BroadcastEvent.sent_at.asc())
        .all()
    )


@autocommit
def create_broadcast_provider_message(broadcast_event, provider):
    broadcast_provider_message_id = uuid.uuid4()
    provider_message = BroadcastProviderMessage(
        id=broadcast_provider_message_id,
        broadcast_event=broadcast_event,
        provider=provider,
        status=BroadcastProviderMessageStatus.SENDING,
    )
    db.session.add(provider_message)
    db.session.commit()
    provider_message_number = None
    if provider == BroadcastProvider.VODAFONE:
        provider_message_number = BroadcastProviderMessageNumber(
            broadcast_provider_message_id=broadcast_provider_message_id
        )
        db.session.add(provider_message_number)
        db.session.commit()
    return provider_message


@autocommit
def update_broadcast_provider_message_status(broadcast_provider_message, *, status):
    broadcast_provider_message.status = status
