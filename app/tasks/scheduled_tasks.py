import time
from datetime import datetime, timedelta, timezone

from emergency_alerts_utils.clients.slack.slack_client import SlackMessage
from emergency_alerts_utils.tasks import QueueNames, TaskNames
from flask import current_app
from periodiq import cron
from sqlalchemy.exc import SQLAlchemyError

from app import db, dramatiq, slack_client
from app.broadcast_message.utils import purge_broadcast_messages
from app.dao.api_key_dao import (
    dao_get_api_keys_needing_expiry_warning,
    dao_record_api_key_expiry_warning_sent,
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
from app.models import (
    API_KEY_MAX_AGE_MONTHS,
    BroadcastMessage,
    BroadcastStatusType,
    Event,
)
from app.publish_task_progress.rest import purge_publish_tasks
from app.status.healthcheck import (
    get_db_version,
    post_app_version_to_cloudwatch,
    post_db_version_to_cloudwatch,
)
from app.tasks.broadcast_message_tasks import (
    trigger_link_test_primary_to_A,
    trigger_link_test_primary_to_B,
    trigger_link_test_secondary_to_A,
    trigger_link_test_secondary_to_B,
)
from app.tasks.govuk_tasks import (
    publish_govuk_build,
    publish_govuk_build_full,
)
from app.utils import is_public_environment


@dramatiq.actor(actor_name=TaskNames.RUN_HEALTH_CHECK, queue_name=QueueNames.PERIODIC, periodic=cron("*/1 * * * *"))
def run_health_check():
    try:
        post_app_version_to_cloudwatch()
        post_db_version_to_cloudwatch(get_db_version())

        time_stamp = int(time.time())
        with open("/eas/emergency-alerts-api/celery-beat-healthcheck", mode="w") as file:
            file.write(str(time_stamp))
        current_app.logger.info(f"file.write successful - celery health check timestamp: {time_stamp}")
    except Exception:
        current_app.logger.exception("Unable to generate health-check timestamp", extra={"python_module": __name__})
        raise


@dramatiq.actor(actor_name=TaskNames.DELETE_VERIFY_CODES, queue_name=QueueNames.PERIODIC, periodic=cron("10 * * * *"))
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


@dramatiq.actor(actor_name=TaskNames.DELETE_INVITATIONS, queue_name=QueueNames.PERIODIC, periodic=cron("20 * * * *"))
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


@dramatiq.actor(actor_name=TaskNames.TRIGGER_LINK_TESTS, queue_name=QueueNames.PERIODIC, periodic=cron("*/3 * * * *"))
def trigger_link_tests():
    if current_app.config["CBC_PROXY_ENABLED"]:
        current_app.logger.info(
            "trigger_link_tests", extra={"python_module": __name__, "target_queue": QueueNames.BROADCASTS}
        )
        for cbc_name in current_app.config["ENABLED_CBCS"]:
            trigger_link_test_primary_to_A.send(provider=cbc_name)
            trigger_link_test_primary_to_B.send(provider=cbc_name)
            trigger_link_test_secondary_to_A.send(provider=cbc_name)
            trigger_link_test_secondary_to_B.send(provider=cbc_name)


def auto_expire_broadcast_messages():
    expired_broadcasts = BroadcastMessage.query.filter(
        BroadcastMessage.finishes_at <= datetime.now(),
        BroadcastMessage.status == BroadcastStatusType.BROADCASTING,
    ).all()

    for broadcast in expired_broadcasts:
        broadcast.status = BroadcastStatusType.COMPLETED
        broadcast.finished_govuk_acknowledged = False

    db.session.commit()


@dramatiq.actor(
    actor_name=TaskNames.REMOVE_YESTERDAYS_PLANNED_TESTS_ON_GOVUK_ALERTS,
    queue_name=QueueNames.PERIODIC,
    periodic=cron("0 0 * * *"),
)
def remove_yesterdays_planned_tests_on_govuk_alerts():
    # Before removing yesterdays planned tests and triggering republish
    # of gov.uk/alerts, the publish tasks from older than 1 day ago are
    # purged from the `publish_task_progress` table
    purge_publish_tasks(days_older_than=1)

    publish_pending, publish_task = publish_govuk_build_full()
    current_app.logger.info(
        "Enqueued full publish GOV UK Alerts for nightly rebuild: %s / %s",
        publish_pending.serialize(),
        publish_task.asdict(),
    )


@dramatiq.actor(
    actor_name=TaskNames.DELETE_OLD_RECORDS_FROM_EVENTS_TABLE,
    queue_name=QueueNames.PERIODIC,
    periodic=cron("0 3 * * *"),
)
def delete_old_records_from_events_table():
    delete_events_before = datetime.now(timezone.utc) - timedelta(weeks=52)
    event_query = Event.query.filter(Event.created_at < delete_events_before)

    deleted_count = event_query.delete()

    current_app.logger.info(
        f"Deleted {deleted_count} events older than {delete_events_before}.",
        extra={
            "python_module": __name__,
            "task": "delete-old-records-from-events-table",
            "target_queue": QueueNames.PERIODIC,
        },
    )

    db.session.commit()


@dramatiq.actor(
    actor_name=TaskNames.VALIDATE_FUNCTIONAL_TEST_ACCOUNT_EMAILS,
    queue_name=QueueNames.PERIODIC,
    periodic=cron("0 0 1 * *"),
)
def validate_functional_test_account_emails():
    emails = []
    for i in range(1, 7):  # 1-6
        emails.append(f"emergency-alerts-tests+user{i}@digital.cabinet-office.gov.uk")
    emails.append("emergency-alerts-tests+webauthn@digital.cabinet-office.gov.uk")
    emails.append("emergency-alerts-tests-admin@digital.cabinet-office.gov.uk")
    emails.append("emergency-alerts-tests-admin+2@digital.cabinet-office.gov.uk")

    try:
        for email in emails:
            user = get_user_by_email(email)
            save_model_user(user, validated_email_access=True)
    except SQLAlchemyError as e:
        current_app.logger.exception(e)
    else:
        current_app.logger.info(
            f"Functional test account emails validated on {datetime.now(timezone.utc).date}",
            extra={
                "python_module": __name__,
                "task": "validate-functional-test-account-emails",
                "target_queue": QueueNames.PERIODIC,
            },
        )


@dramatiq.actor(
    actor_name=TaskNames.QUEUE_AFTER_ALERT_ACTIVITIES, queue_name=QueueNames.PERIODIC, periodic=cron("*/1 * * * *")
)
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
            publish_pending, publish_task = publish_govuk_build()
            if publish_task is not None:
                current_app.logger.info(
                    "Enqueued publish GOV UK Alerts: %s, %s", publish_pending.serialize(), publish_task.asdict()
                )
            else:
                current_app.logger.info(
                    "*Not* queued a publish to GOV UK Alerts, one or more pending tasks already: %s",
                    publish_pending.serialize(),
                )


@dramatiq.actor(
    actor_name=TaskNames.PURGE_FUNCTIONAL_TEST_ALERTS,
    queue_name=QueueNames.PERIODIC,
    periodic=cron("0 4 * * *"),
)
def purge_functional_test_alerts(older_than=1):
    """
    Purge alerts created by functional tests daily.
    This is housekeeping to reduce the number of alerts that GovUK and admin has to deal with.
    """

    if is_public_environment():
        current_app.logger.info("Skipping purge of functional test broadcasts - this is a public environment")
        return

    functional_tests_service_id = current_app.config.get("FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID")
    if functional_tests_service_id is None:
        current_app.logger.warning("No FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID? Can't purge functional test alerts")
        # If we give none to the purge method it'll do it for all services, so bail.
        return

    current_app.logger.info(
        f"Starting purge of alerts older than {older_than} days in service {functional_tests_service_id}"
    )
    purge_broadcast_messages(service_id=functional_tests_service_id, older_than=older_than)
    current_app.logger.info("Finished purge")


@dramatiq.actor(
    actor_name=TaskNames.PURGE_OLD_ALERTS_FROM_PREVIEW_ENVIRONMENT,
    queue_name=QueueNames.PERIODIC,
    periodic=cron("15 10 * * 2"),  # Every Tuesday at 10:15 UTC
)
def purge_old_alerts_from_preview_environment():
    """
    Purge old alerts from the preview environment.
    Preview already purges the alerts created by the functional test
    service; this task purges any other alerts that may have been
    created manually or through the API.
    As the non-test alerts may be supporting long-termmanual testing
    activities, we only purge alerts older that 1 year.
    """
    if current_app.config["ENVIRONMENT"] == "preview":
        try:
            purge_broadcast_messages(service_id=None, older_than=365)
            current_app.logger.info("Purged messages older than 1 year from preview environment")
        except Exception as e:
            current_app.logger.exception(f"Unable to purge preview messages: {e}")
            raise


@dramatiq.actor(
    actor_name=TaskNames.CHECK_API_KEY_EXPIRY,
    queue_name=QueueNames.PERIODIC,
    periodic=cron("0 9 * * 1-5"),  # 09:00 UTC, Monday to Friday
)
def check_api_key_expiry():
    """
    Each key is warned about once and a key whose warning window opens at the
    weekend (or while this task isn't running) is picked up on the next run.
    """
    webhook_url = current_app.config.get("API_KEY_EXPIRY_SLACK_WEBHOOK_URL")
    if not webhook_url:
        current_app.logger.info(
            "Skipping API key expiry check - no Slack webhook configured for this environment",
            extra={"python_module": __name__},
        )
        return
    if not webhook_url.startswith("https://"):
        # e.g. the "dummy" value Terraform creates the SSM parameter with, before it's been set
        current_app.logger.error(
            "Skipping API key expiry check - API_KEY_EXPIRY_SLACK_WEBHOOK_URL is not a valid webhook URL",
            extra={"python_module": __name__},
        )
        return

    today = datetime.now(timezone.utc).date()
    api_keys = dao_get_api_keys_needing_expiry_warning(today)
    current_app.logger.info(
        f"Found {len(api_keys)} API keys needing an expiry warning",
        extra={"python_module": __name__, "task": TaskNames.CHECK_API_KEY_EXPIRY},
    )

    for api_key in api_keys:
        # Send before recording, so a failure means a retry rather than a missed warning
        slack_client.send_message_to_slack(_api_key_expiry_slack_message(webhook_url, api_key, today))
        dao_record_api_key_expiry_warning_sent(api_key)
        current_app.logger.info(
            f"Sent expiry warning for API key {api_key.id} in service {api_key.service_id}",
            extra={"python_module": __name__, "task": TaskNames.CHECK_API_KEY_EXPIRY},
        )


def _api_key_expiry_slack_message(webhook_url, api_key, today):
    expires_on = api_key.scheduled_expiry_date
    days_left = (expires_on - today).days
    service = api_key.service

    if days_left > 0:
        subject = f"API key expires in {days_left} day{'' if days_left == 1 else 's'}"
        message_type = "info"
        action = (
            f"Work with the client to replace this key, then revoke it on {expires_on:%-d %B %Y} "
            f"when it reaches {API_KEY_MAX_AGE_MONTHS} months old."
        )
    else:
        subject = "API key expires today" if days_left == 0 else "API key is past its expiry date"
        message_type = "error"
        action = (
            f"This key has reached {API_KEY_MAX_AGE_MONTHS} months old. "
            "Work with the client to replace it, then revoke it as soon as possible."
        )

    sections = [
        f"*Environment:* {current_app.config.get('ENVIRONMENT')}",
        f"*Service:* {_slack_escape(service.name)} (`{service.id}`)",
        f"*Key name:* {_slack_escape(api_key.name)}",
        f"*Key type:* {api_key.key_type}",
        f"*Created:* {api_key.created_at:%-d %B %Y}",
        f"*Expires:* {expires_on:%-d %B %Y}",
        action,
    ]
    if admin_url := current_app.config.get("ADMIN_EXTERNAL_URL"):
        sections.append(f"<{admin_url}/services/{service.id}/api/keys|View API keys for this service>")

    return SlackMessage(
        webhook_url=webhook_url,
        subject=subject,
        message_type=message_type,
        markdown_sections=sections,
    )


def _slack_escape(text):
    # Names are entered by users; these are the only characters Slack mrkdwn needs escaping
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
