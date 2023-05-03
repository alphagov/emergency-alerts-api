import time
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app import db, notify_celery
from app.celery.broadcast_message_tasks import trigger_link_test
from app.config import QueueNames, TaskNames
from app.cronitor import cronitor
from app.dao.invited_org_user_dao import (
    delete_org_invitations_created_more_than_two_days_ago,
)
from app.dao.invited_user_dao import (
    delete_invitations_created_more_than_two_days_ago,
)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.models import BroadcastMessage, BroadcastStatusType, Event


@notify_celery.task(name="run-health-check")
def run_health_check(message):
    try:
        time_stamp = int(time.time())
        with open("/eas/emergency-alerts-api/celery-beat-healthcheck", mode="w") as file:
            file.write(str(time_stamp))
        message.ack()
    except Exception:
        current_app.logger.exception("Unable to generate health-check timestamp")
        raise


@notify_celery.task(name="delete-verify-codes")
def delete_verify_codes():
    try:
        start = datetime.utcnow()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} verify codes".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete verify codes")
        raise


@notify_celery.task(name="delete-invitations")
def delete_invitations():
    try:
        start = datetime.utcnow()
        deleted_invites = delete_invitations_created_more_than_two_days_ago()
        deleted_invites += delete_org_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} invitations".format(start, datetime.utcnow(), deleted_invites)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name="trigger-link-tests")
def trigger_link_tests():
    if current_app.config["CBC_PROXY_ENABLED"]:
        for cbc_name in current_app.config["ENABLED_CBCS"]:
            trigger_link_test.apply_async(kwargs={"provider": cbc_name}, queue=QueueNames.BROADCASTS)


@notify_celery.task(name="auto-expire-broadcast-messages")
def auto_expire_broadcast_messages():
    expired_broadcasts = BroadcastMessage.query.filter(
        BroadcastMessage.finishes_at <= datetime.now(),
        BroadcastMessage.status == BroadcastStatusType.BROADCASTING,
    ).all()

    for broadcast in expired_broadcasts:
        broadcast.status = BroadcastStatusType.COMPLETED

    db.session.commit()

    if expired_broadcasts:
        notify_celery.send_task(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)


@notify_celery.task(name="remove-yesterdays-planned-tests-on-govuk-alerts")
def remove_yesterdays_planned_tests_on_govuk_alerts():
    notify_celery.send_task(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)


@notify_celery.task(name="delete-old-records-from-events-table")
@cronitor("delete-old-records-from-events-table")
def delete_old_records_from_events_table():
    delete_events_before = datetime.utcnow() - timedelta(weeks=52)
    event_query = Event.query.filter(Event.created_at < delete_events_before)

    deleted_count = event_query.delete()

    current_app.logger.info(f"Deleted {deleted_count} historical events from before {delete_events_before}.")

    db.session.commit()
