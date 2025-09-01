import time
from datetime import datetime, timedelta, timezone

from emergency_alerts_utils.celery import QueueNames, TaskNames
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app import db, notify_celery

# from app.celery.broadcast_message_tasks import trigger_link_test
from app.celery.broadcast_message_tasks import (
    trigger_link_test_primary_to_A,
    trigger_link_test_primary_to_B,
    trigger_link_test_secondary_to_A,
    trigger_link_test_secondary_to_B,
)
from app.dao.broadcast_message_dao import (
    dao_get_all_finished_broadcast_messages_with_outstanding_actions,
)
from app.dao.invited_org_user_dao import (
    delete_org_invitations_created_more_than_two_days_ago,
)
from app.dao.invited_user_dao import (
    delete_invitations_created_more_than_two_days_ago,
)
from app.dao.users_dao import (
    delete_codes_older_created_more_than_a_day_ago,
    get_user_by_email,
    save_model_user,
)
from app.models import BroadcastMessage, BroadcastStatusType, Event
from app.status.healthcheck import post_version_to_cloudwatch


@notify_celery.task(name=TaskNames.RUN_HEALTH_CHECK)
def run_health_check():
    try:
        post_version_to_cloudwatch()

        time_stamp = int(time.time())
        with open("/eas/emergency-alerts-api/celery-beat-healthcheck", mode="w") as file:
            file.write(str(time_stamp))
        current_app.logger.info(f"file.write successful - celery health check timestamp: {time_stamp}")
    except Exception:
        current_app.logger.exception("Unable to generate health-check timestamp", extra={"python_module": __name__})
        raise


@notify_celery.task(name=TaskNames.DELETE_VERIFY_CODES)
def delete_verify_codes():
    try:
        start = datetime.now(timezone.utc)
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            f"Delete job started {start} finished {datetime.now(timezone.utc)} deleted {deleted} verify codes",
            extra={"python_module": __name__},
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete verify codes", extra={"python_module": __name__})
        raise


@notify_celery.task(name=TaskNames.DELETE_INVITATIONS)
def delete_invitations():
    try:
        start = datetime.now(timezone.utc)
        deleted_invites = delete_invitations_created_more_than_two_days_ago()
        deleted_invites += delete_org_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            f"Delete job started {start} finished {datetime.now(timezone.utc)} deleted {deleted_invites} invitations",
            extra={"python_module": __name__},
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations", extra={"python_module": __name__})
        raise


@notify_celery.task(name=TaskNames.TRIGGER_LINK_TESTS)
def trigger_link_tests():
    if current_app.config["CBC_PROXY_ENABLED"]:
        current_app.logger.info(
            "trigger_link_tests", extra={"python_module": __name__, "target_queue": QueueNames.BROADCASTS}
        )
        for cbc_name in current_app.config["ENABLED_CBCS"]:
            # trigger_link_test.apply_async(kwargs={"provider": cbc_name}, queue=QueueNames.BROADCASTS)
            trigger_link_test_primary_to_A.apply_async(kwargs={"provider": cbc_name}, queue=QueueNames.BROADCASTS)
            trigger_link_test_primary_to_B.apply_async(kwargs={"provider": cbc_name}, queue=QueueNames.BROADCASTS)
            trigger_link_test_secondary_to_A.apply_async(kwargs={"provider": cbc_name}, queue=QueueNames.BROADCASTS)
            trigger_link_test_secondary_to_B.apply_async(kwargs={"provider": cbc_name}, queue=QueueNames.BROADCASTS)


def auto_expire_broadcast_messages():
    expired_broadcasts = BroadcastMessage.query.filter(
        BroadcastMessage.finishes_at <= datetime.now(),
        BroadcastMessage.status == BroadcastStatusType.BROADCASTING,
    ).all()

    for broadcast in expired_broadcasts:
        broadcast.status = BroadcastStatusType.COMPLETED
        broadcast.finished_govuk_acknowledged = False

    db.session.commit()


@notify_celery.task(name=TaskNames.REMOVE_YESTERDAYS_PLANNED_TESTS_ON_GOVUK_ALERTS)
def remove_yesterdays_planned_tests_on_govuk_alerts():
    current_app.logger.info(
        "remove_yesterdays_planned_tests_on_govuk_alerts",
        extra={
            "python_module": __name__,
            "send_task": TaskNames.PUBLISH_GOVUK_ALERTS,
            "target_queue": QueueNames.GOVUK_ALERTS,
        },
    )
    notify_celery.send_task(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)


@notify_celery.task(name=TaskNames.DELETE_OLD_RECORDS_FROM_EVENTS_TABLE)
def delete_old_records_from_events_table():
    delete_events_before = datetime.now(timezone.utc) - timedelta(weeks=52)
    event_query = Event.query.filter(Event.created_at < delete_events_before)

    deleted_count = event_query.delete()

    current_app.logger.info(
        f"Deleted {deleted_count} events older than {delete_events_before}.",
        extra={
            "python_module": __name__,
            "celery_task": "delete-old-records-from-events-table",
            "target_queue": QueueNames.PERIODIC,
        },
    )

    db.session.commit()


@notify_celery.task(name=TaskNames.VALIDATE_FUNCTIONAL_TEST_ACCOUNT_EMAILS)
def validate_functional_test_account_emails():
    try:
        user1 = get_user_by_email("emergency-alerts-tests+user1@digital.cabinet-office.gov.uk")
        save_model_user(user1, validated_email_access=True)
        user2 = get_user_by_email("emergency-alerts-tests+user2@digital.cabinet-office.gov.uk")
        save_model_user(user2, validated_email_access=True)
        user3 = get_user_by_email("emergency-alerts-tests+user3@digital.cabinet-office.gov.uk")
        save_model_user(user3, validated_email_access=True)
        user4 = get_user_by_email("emergency-alerts-tests+user4@digital.cabinet-office.gov.uk")
        save_model_user(user4, validated_email_access=True)
        user5 = get_user_by_email("emergency-alerts-tests+user5@digital.cabinet-office.gov.uk")
        save_model_user(user5, validated_email_access=True)
        user6 = get_user_by_email("emergency-alerts-tests+user6@digital.cabinet-office.gov.uk")
        save_model_user(user6, validated_email_access=True)
        admin = get_user_by_email("emergency-alerts-tests-admin@digital.cabinet-office.gov.uk")
        save_model_user(admin, validated_email_access=True)
        admin2 = get_user_by_email("emergency-alerts-tests-admin+2@digital.cabinet-office.gov.uk")
        save_model_user(admin2, validated_email_access=True)
    except SQLAlchemyError as e:
        current_app.logger.exception(e)
    else:
        current_app.logger.info(
            f"Functional test account emails validated on {datetime.now(timezone.utc).date}",
            extra={
                "python_module": __name__,
                "celery_task": "validate-functional-test-account-emails",
                "target_queue": QueueNames.PERIODIC,
            },
        )


@notify_celery.task(name=TaskNames.QUEUE_AFTER_ALERT_ACTIVITIES)
def queue_after_alert_activities():
    """Check for any recently expired alerts and process any activities that are due on them"""

    auto_expire_broadcast_messages()

    # Find recently expired which have one or more actions due
    expired_and_pending_alerts = dao_get_all_finished_broadcast_messages_with_outstanding_actions()

    current_app.logger.info(
        "There are %d recently expired/cancelled alerts with pending activities", len(expired_and_pending_alerts)
    )

    if len(expired_and_pending_alerts) > 0:
        if any(not x.finished_govuk_acknowledged for x in expired_and_pending_alerts):
            # This need not be idempotent as any regeneration is 'free', and we rely upon
            # GovUK calling us back to mark the action as 'done' instead of just assuming.
            current_app.logger.info("Requesting GovUK publish")
            notify_celery.send_task(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)

        # Down the line we will look to request logs from MNOs
