from datetime import datetime, timedelta

from emergency_alerts_utils.clients.zendesk.zendesk_client import (
    EASSupportTicket,
)
from emergency_alerts_utils.timezones import convert_utc_to_bst
from flask import current_app
from sqlalchemy import func

from app import notify_celery, statsd_client, zendesk_client
from app.aws import s3
from app.config import QueueNames
from app.cronitor import cronitor
from app.dao.fact_processing_time_dao import insert_update_processing_time
from app.dao.jobs_dao import (
    dao_archive_job,
    dao_get_jobs_older_than_data_retention,
)
from app.dao.notifications_dao import (
    dao_get_notifications_processing_time_stats,
    dao_timeout_notifications,
    get_service_ids_with_notifications_before,
    move_notifications_to_notification_history,
)
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention_for_all_services_by_notification_type,
)
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_SENDING,
    SMS_TYPE,
    FactProcessingTime,
    Notification,
)
from app.notifications.notifications_ses_callback import (
    check_and_queue_callback_task,
)
from app.utils import get_london_midnight_in_utc


@notify_celery.task(name="remove_sms_email_jobs")
@cronitor("remove_sms_email_jobs")
def remove_sms_email_csv_files():
    _remove_csv_files([EMAIL_TYPE, SMS_TYPE])


def _remove_csv_files(job_types):
    jobs = dao_get_jobs_older_than_data_retention(notification_types=job_types)
    for job in jobs:
        s3.remove_job_from_s3(job.service_id, job.id)
        dao_archive_job(job)
        current_app.logger.info("Job ID {} has been removed from s3.".format(job.id))


@notify_celery.task(name="delete-notifications-older-than-retention")
def delete_notifications_older_than_retention():
    delete_email_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)
    delete_sms_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)
    delete_letter_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)


@notify_celery.task(name="delete-sms-notifications")
@cronitor("delete-sms-notifications")
def delete_sms_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type("sms")


@notify_celery.task(name="delete-email-notifications")
@cronitor("delete-email-notifications")
def delete_email_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type("email")


@notify_celery.task(name="delete-letter-notifications")
@cronitor("delete-letter-notifications")
def delete_letter_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type("letter")


def _delete_notifications_older_than_retention_by_type(notification_type):
    flexible_data_retention = fetch_service_data_retention_for_all_services_by_notification_type(notification_type)

    for f in flexible_data_retention:
        day_to_delete_backwards_from = get_london_midnight_in_utc(
            convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=f.days_of_retention)
        )

        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": f.service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": day_to_delete_backwards_from,
            },
        )

    seven_days_ago = get_london_midnight_in_utc(convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=7))
    service_ids_with_data_retention = {x.service_id for x in flexible_data_retention}

    # get a list of all service ids that we'll need to delete for. Typically that might only be 5% of services.
    # This query takes a couple of mins to run.
    service_ids_that_have_sent_notifications_recently = get_service_ids_with_notifications_before(
        notification_type, seven_days_ago
    )

    service_ids_to_purge = service_ids_that_have_sent_notifications_recently - service_ids_with_data_retention

    for service_id in service_ids_to_purge:
        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": seven_days_ago,
            },
        )

    current_app.logger.info(
        f"delete-notifications-older-than-retention: triggered subtasks for notification_type {notification_type}: "
        f"{len(service_ids_with_data_retention)} services with flexible data retention, "
        f"{len(service_ids_to_purge)} services without flexible data retention"
    )


@notify_celery.task(name="delete-notifications-for-service-and-type")
def delete_notifications_for_service_and_type(service_id, notification_type, datetime_to_delete_before):
    start = datetime.utcnow()
    num_deleted = move_notifications_to_notification_history(
        notification_type,
        service_id,
        datetime_to_delete_before,
    )
    if num_deleted:
        end = datetime.utcnow()
        current_app.logger.info(
            f"delete-notifications-for-service-and-type: "
            f"service: {service_id}, "
            f"notification_type: {notification_type}, "
            f"count deleted: {num_deleted}, "
            f"duration: {(end - start).seconds} seconds"
        )


@notify_celery.task(name="timeout-sending-notifications")
@cronitor("timeout-sending-notifications")
def timeout_notifications():
    notifications = ["dummy value so len() > 0"]

    cutoff_time = datetime.utcnow() - timedelta(seconds=current_app.config.get("SENDING_NOTIFICATIONS_TIMEOUT_PERIOD"))

    while len(notifications) > 0:
        notifications = dao_timeout_notifications(cutoff_time)

        for notification in notifications:
            statsd_client.incr(f"timeout-sending.{notification.sent_by}")
            check_and_queue_callback_task(notification)

        current_app.logger.info(
            "Timeout period reached for {} notifications, status has been updated.".format(len(notifications))
        )


@notify_celery.task(name="raise-alert-if-letter-notifications-still-sending")
@cronitor("raise-alert-if-letter-notifications-still-sending")
def raise_alert_if_letter_notifications_still_sending():
    still_sending_count, sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()

    if still_sending_count:
        message = "There are {} letters in the 'sending' state from {}".format(
            still_sending_count, sent_date.strftime("%A %d %B")
        )

        if current_app.should_send_zendesk_alerts:
            message += ". Resolve using https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-letters-still-in-sending"  # noqa

            ticket = EASSupportTicket(
                subject=f"[{current_app.config['HOST']}] Letters still sending",
                email_ccs=current_app.config["DVLA_EMAIL_ADDRESSES"],
                message=message,
                ticket_type=EASSupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
        else:
            current_app.logger.info(message)


def get_letter_notifications_still_sending_when_they_shouldnt_be():
    today = datetime.utcnow().date()

    # Do nothing on the weekend
    if today.isoweekday() in {6, 7}:  # sat, sun
        return 0, None

    if today.isoweekday() in {1, 2}:  # mon, tues. look for files from before the weekend
        offset_days = 4
    else:
        offset_days = 2

    expected_sent_date = today - timedelta(days=offset_days)

    q = Notification.query.filter(
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_SENDING,
        Notification.key_type == KEY_TYPE_NORMAL,
        func.date(Notification.sent_at) <= expected_sent_date,
    )

    return q.count(), expected_sent_date


@notify_celery.task(name="save-daily-notification-processing-time")
@cronitor("save-daily-notification-processing-time")
def save_daily_notification_processing_time(bst_date=None):
    # bst_date is a string in the format of "YYYY-MM-DD"
    if bst_date is None:
        # if a date is not provided, we run against yesterdays data
        bst_date = (datetime.utcnow() - timedelta(days=1)).date()
    else:
        bst_date = datetime.strptime(bst_date, "%Y-%m-%d").date()

    start_time = get_london_midnight_in_utc(bst_date)
    end_time = get_london_midnight_in_utc(bst_date + timedelta(days=1))
    result = dao_get_notifications_processing_time_stats(start_time, end_time)
    insert_update_processing_time(
        FactProcessingTime(
            bst_date=bst_date,
            messages_total=result.messages_total,
            messages_within_10_secs=result.messages_within_10_secs,
        )
    )
