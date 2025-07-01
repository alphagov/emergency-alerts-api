import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import and_, asc, case, desc, or_
from sqlalchemy.orm import aliased

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
    User,
)


def dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id):
    return BroadcastMessage.query.filter(
        BroadcastMessage.id == broadcast_message_id, BroadcastMessage.service_id == service_id
    ).one()


def dao_get_broadcast_message_by_id_and_service_id_with_user(broadcast_message_id, service_id):
    """
    This function returns a tuple that consists of BroadcastMessage and additional values
    for created_by, rejected_by, approved_by & cancelled_by.
    These values are the names of the users sourced using joins with User table.
    """

    UserCreated = aliased(User)
    UserRejected = aliased(User)
    UserApproved = aliased(User)
    UserCancelled = aliased(User)
    UserSubmitted = aliased(User)
    UserUpdated = aliased(User)

    return (
        db.session.query(
            BroadcastMessage,
            UserCreated.name.label("created_by"),
            UserRejected.name.label("rejected_by"),
            UserApproved.name.label("approved_by"),
            UserCancelled.name.label("cancelled_by"),
            UserSubmitted.name.label("submitted_by"),
            UserUpdated.name.label("updated_by"),
        )
        .outerjoin(UserCreated, BroadcastMessage.created_by_id == UserCreated.id)
        .outerjoin(UserRejected, BroadcastMessage.rejected_by_id == UserRejected.id)
        .outerjoin(UserApproved, BroadcastMessage.approved_by_id == UserApproved.id)
        .outerjoin(UserCancelled, BroadcastMessage.cancelled_by_id == UserCancelled.id)
        .outerjoin(UserSubmitted, BroadcastMessage.submitted_by_id == UserSubmitted.id)
        .outerjoin(UserUpdated, BroadcastMessage.updated_by_id == UserUpdated.id)
        .filter(BroadcastMessage.id == broadcast_message_id, BroadcastMessage.service_id == service_id)
        .one()
    )


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


def dao_get_broadcast_messages_for_service_with_user(service_id):
    """
    This function returns a list of BroadcastMessages for the service, with additional values
    for created_by, rejected_by, approved_by, cancelled_by & submitted_by.

    The User-related values are the names of the users sourced using joins with User table.
    """
    UserCreated = aliased(User)
    UserRejected = aliased(User)
    UserApproved = aliased(User)
    UserCancelled = aliased(User)
    UserSubmitted = aliased(User)

    """This is the order in which alerts should be displayed on 'Current alerts' page
    and thus the order in which they are sent to Admin application:
    1. Alerts that are live (Broadcasting)
    2. Alerts that have been returned for edit (Returned)
    3. Alerts that are awaiting approval (Pending-approval)
    4. Alerts that are in draft state (Draft)
    """

    status_order = case(
        (BroadcastMessage.status == BroadcastStatusType.BROADCASTING, 1),
        (BroadcastMessage.status == BroadcastStatusType.RETURNED, 2),
        (BroadcastMessage.status == BroadcastStatusType.PENDING_APPROVAL, 3),
        (BroadcastMessage.status == BroadcastStatusType.DRAFT, 4),
    )

    return (
        db.session.query(
            BroadcastMessage,
            UserCreated.name.label("created_by"),
            UserRejected.name.label("rejected_by"),
            UserApproved.name.label("approved_by"),
            UserCancelled.name.label("cancelled_by"),
            UserCancelled.name.label("submitted_by"),
        )
        .outerjoin(UserCreated, BroadcastMessage.created_by_id == UserCreated.id)
        .outerjoin(UserRejected, BroadcastMessage.rejected_by_id == UserRejected.id)
        .outerjoin(UserApproved, BroadcastMessage.approved_by_id == UserApproved.id)
        .outerjoin(UserCancelled, BroadcastMessage.cancelled_by_id == UserCancelled.id)
        .outerjoin(UserSubmitted, BroadcastMessage.submitted_by_id == UserSubmitted.id)
        .filter(BroadcastMessage.service_id == service_id)
        .order_by(
            status_order,
            asc(BroadcastMessage.reference),
        )
        .all()
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


def dao_get_all_pre_broadcast_messages():
    return (
        db.session.query(
            BroadcastMessage.id,
            BroadcastMessage.created_at,
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
            BroadcastMessage.status.in_(BroadcastStatusType.PRE_BROADCAST_STATUSES),
        )
        .order_by(desc(BroadcastMessage.starts_at))
        .all()
    )


def dao_get_all_finished_broadcast_messages_with_outstanding_actions() -> list[BroadcastMessage]:
    """
    Find all BroadcastMessages that have finished (either expired or been cancelled)
    and have one or more flags indicating actions due.
    """

    now = datetime.now(timezone.utc)
    return BroadcastMessage.query.filter(
        and_(
            or_(
                # Get those recently cancelled
                BroadcastMessage.status == BroadcastStatusType.CANCELLED,
                # Or have COMPLETED or are BROADCASTING and have naturally finished
                # (Transitioning to COMPLETED occurs as a background activity)
                BroadcastMessage.status == BroadcastStatusType.COMPLETED,
                and_(
                    BroadcastMessage.finishes_at < now,
                    BroadcastMessage.status == BroadcastStatusType.BROADCASTING,
                ),
            ),
            # And has an action due
            BroadcastMessage.finished_govuk_acknowledged == False,  # noqa: E712
        ),
    ).all()


def dao_purge_old_broadcast_messages(service, days_older_than=30, dry_run=False):
    if service is None:
        raise ValueError("Service ID is required")

    service_id = _resolve_service_id(service)
    if service_id is None:
        raise ValueError("Unable to find service ID")

    print(f"Purging alerts for service {service_id}")
    message_ids = _get_broadcast_messages(days_older_than, service_id)

    counter = {"msgs": 0, "events": 0, "provider_msgs": 0, "msg_numbers": 0}
    for message_id in message_ids:
        try:
            broadcast_event_ids = _get_broadcast_event_ids(message_id)
            broadcast_provider_message_ids = _broadcast_provider_message_ids(broadcast_event_ids)

            if len(broadcast_provider_message_ids):
                counter["msg_numbers"] += _delete_broadcast_provider_message_numbers(
                    broadcast_provider_message_ids, dry_run=dry_run
                )
                counter["provider_msgs"] += _delete_broadcast_provider_messages(
                    broadcast_provider_message_ids, dry_run=dry_run
                )

            if len(broadcast_event_ids):
                counter["events"] += _delete_broadcast_events(broadcast_event_ids, dry_run=dry_run)

            counter["msgs"] += _delete_broadcast_message(message_id, dry_run=dry_run)

            if not dry_run:
                db.session.commit()

        except Exception as e:
            if not dry_run:
                db.session.rollback()
            raise e

    return counter


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


def _resolve_service_id(service):
    if service is None:
        service = uuid.UUID(current_app.config["FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID"])
    else:
        if not isinstance(service, uuid.UUID):
            try:
                service = uuid.UUID(service)
            except ValueError:
                return None

    if db.session.query(Service).filter(Service.id == service).one():
        return str(service)

    return None


def _get_broadcast_messages(days_older_than, service_id):
    messages = (
        db.session.query(
            BroadcastMessage.id,
        )
        .filter(
            BroadcastMessage.service_id == service_id,
            BroadcastMessage.created_at <= datetime.now() - timedelta(days=days_older_than),
            BroadcastMessage.status.in_(BroadcastStatusType.PRE_BROADCAST_STATUSES + BroadcastStatusType.LIVE_STATUSES),
        )
        .all()
    )
    return [str(row[0]) for row in messages]


def _get_broadcast_event_ids(message_id):
    broadcast_event_rows = db.session.query(BroadcastEvent.id).filter_by(broadcast_message_id=message_id).all()
    broadcast_event_ids = [str(row[0]) for row in broadcast_event_rows]
    print(f"BroadcastEvent IDs associated with messsage {message_id}:")
    if len(broadcast_event_ids):
        print("\n".join(broadcast_event_ids))
    else:
        print("None")

    return broadcast_event_ids


def _broadcast_provider_message_ids(broadcast_event_ids):
    broadcast_provider_message_rows = (
        db.session.query(BroadcastProviderMessage.id)
        .filter(BroadcastProviderMessage.broadcast_event_id.in_(broadcast_event_ids))
        .all()
    )
    broadcast_provider_message_ids = [str(row[0]) for row in broadcast_provider_message_rows]

    return broadcast_provider_message_ids


def _delete_broadcast_provider_message_numbers(broadcast_provider_message_ids, dry_run=False):
    bpmn = db.session.query(BroadcastProviderMessageNumber).filter(
        BroadcastProviderMessageNumber.broadcast_provider_message_id.in_(broadcast_provider_message_ids)
    )
    item_count = len(bpmn.all())
    if not dry_run:
        bpmn.delete(synchronize_session=False)
    return item_count


def _delete_broadcast_provider_messages(broadcast_provider_message_ids, dry_run=False):
    bpm = db.session.query(BroadcastProviderMessage).filter(
        BroadcastProviderMessage.id.in_(broadcast_provider_message_ids)
    )
    item_count = len(bpm.all())
    if not dry_run:
        bpm.delete(synchronize_session=False)
    return item_count


def _delete_broadcast_events(broadcast_event_ids, dry_run=False):
    be = db.session.query(BroadcastEvent).filter(BroadcastEvent.id.in_(broadcast_event_ids))
    if not dry_run:
        be.delete(synchronize_session=False)
    return len(broadcast_event_ids)


def _delete_broadcast_message(message_id, dry_run=False):
    bm = db.session.query(BroadcastMessage).filter_by(id=message_id)
    if not dry_run:
        bm.delete(synchronize_session=False)
    return 1
