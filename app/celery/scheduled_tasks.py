from collections import defaultdict
from datetime import datetime, timedelta

import jinja2
from flask import current_app
from emergency_alerts_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
)
from sqlalchemy import between
from sqlalchemy.exc import SQLAlchemyError

from app import db, notify_celery, zendesk_client
from app.aws import s3
from app.celery.broadcast_message_tasks import trigger_link_test
from app.celery.letters_pdf_tasks import get_pdf_for_templated_letter
from app.celery.tasks import (
    get_recipient_csv_and_template_and_sender_id,
    process_incomplete_jobs,
    process_job,
    process_row,
)
from app.config import QueueNames, TaskNames
from app.cronitor import cronitor
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers
from app.dao.invited_org_user_dao import (
    delete_org_invitations_created_more_than_two_days_ago,
)
from app.dao.invited_user_dao import (
    delete_invitations_created_more_than_two_days_ago,
)
from app.dao.jobs_dao import (
    dao_set_scheduled_jobs_to_pending,
    dao_update_job,
    find_jobs_with_missing_rows,
    find_missing_row_for_job,
)
from app.dao.notifications_dao import (
    dao_old_letters_with_created_status,
    dao_precompiled_letters_still_pending_virus_check,
    is_delivery_slow_for_providers,
    letters_missing_from_sending_bucket,
    notifications_not_yet_sent,
)
from app.dao.provider_details_dao import (
    dao_adjust_provider_priority_back_to_resting_points,
    dao_reduce_sms_provider_priority,
)
from app.dao.services_dao import (
    dao_find_services_sending_to_tv_numbers,
    dao_find_services_with_high_failure_rates,
)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.letters.utils import generate_letter_pdf_filename
from app.models import (
    EMAIL_TYPE,
    JOB_STATUS_ERROR,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    SMS_TYPE,
    BroadcastMessage,
    BroadcastStatusType,
    EmailBranding,
    Event,
    Job,
    Organisation,
)
from app.notifications.process_notifications import send_notification_to_queue


@notify_celery.task(name="run-scheduled-jobs")
@cronitor("run-scheduled-jobs")
def run_scheduled_jobs():
    try:
        for job in dao_set_scheduled_jobs_to_pending():
            process_job.apply_async([str(job.id)], queue=QueueNames.JOBS)
            current_app.logger.info("Job ID {} added to process job queue".format(job.id))
    except SQLAlchemyError:
        current_app.logger.exception("Failed to run scheduled jobs")
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


@notify_celery.task(name="switch-current-sms-provider-on-slow-delivery")
def switch_current_sms_provider_on_slow_delivery():
    """
    Reduce provider's priority if at least 30% of notifications took more than four minutes to be delivered
    in the last ten minutes. If both providers are slow, don't do anything. If we changed the providers in the
    last ten minutes, then don't update them again either.
    """
    slow_delivery_notifications = is_delivery_slow_for_providers(
        threshold=0.3,
        created_at=datetime.utcnow() - timedelta(minutes=10),
        delivery_time=timedelta(minutes=4),
    )

    # only adjust if some values are true and some are false - ie, don't adjust if all providers are fast or
    # all providers are slow
    if len(set(slow_delivery_notifications.values())) != 1:
        for provider_name, is_slow in slow_delivery_notifications.items():
            if is_slow:
                current_app.logger.warning("Slow delivery notifications detected for provider {}".format(provider_name))
                dao_reduce_sms_provider_priority(provider_name, time_threshold=timedelta(minutes=10))


@notify_celery.task(name="tend-providers-back-to-middle")
def tend_providers_back_to_middle():
    dao_adjust_provider_priority_back_to_resting_points()


@notify_celery.task(name="check-job-status")
def check_job_status():
    """
    every x minutes do this check
    select
    from jobs
    where job_status == 'in progress'
    and processing started between 30 and 35 minutes ago
    OR where the job_status == 'pending'
    and the job scheduled_for timestamp is between 30 and 35 minutes ago.
    if any results then
        update the job_status to 'error'
        process the rows in the csv that are missing (in another task) just do the check here.
    """
    thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
    thirty_five_minutes_ago = datetime.utcnow() - timedelta(minutes=35)

    incomplete_in_progress_jobs = Job.query.filter(
        Job.job_status == JOB_STATUS_IN_PROGRESS,
        between(Job.processing_started, thirty_five_minutes_ago, thirty_minutes_ago),
    )
    incomplete_pending_jobs = Job.query.filter(
        Job.job_status == JOB_STATUS_PENDING,
        Job.scheduled_for.isnot(None),
        between(Job.scheduled_for, thirty_five_minutes_ago, thirty_minutes_ago),
    )

    jobs_not_complete_after_30_minutes = (
        incomplete_in_progress_jobs.union(incomplete_pending_jobs)
        .order_by(Job.processing_started, Job.scheduled_for)
        .all()
    )

    # temporarily mark them as ERROR so that they don't get picked up by future check_job_status tasks
    # if they haven't been re-processed in time.
    job_ids = []
    for job in jobs_not_complete_after_30_minutes:
        job.job_status = JOB_STATUS_ERROR
        dao_update_job(job)
        job_ids.append(str(job.id))

    if job_ids:
        current_app.logger.info("Job(s) {} have not completed.".format(job_ids))
        process_incomplete_jobs.apply_async([job_ids], queue=QueueNames.JOBS)


@notify_celery.task(name="replay-created-notifications")
def replay_created_notifications():
    # if the notification has not be send after 1 hour, then try to resend.
    resend_created_notifications_older_than = 60 * 60
    for notification_type in (EMAIL_TYPE, SMS_TYPE):
        notifications_to_resend = notifications_not_yet_sent(resend_created_notifications_older_than, notification_type)

        if len(notifications_to_resend) > 0:
            current_app.logger.info(
                "Sending {} {} notifications "
                "to the delivery queue because the notification "
                "status was created.".format(len(notifications_to_resend), notification_type)
            )

        for n in notifications_to_resend:
            send_notification_to_queue(notification=n, research_mode=n.service.research_mode)

    # if the letter has not be send after an hour, then create a zendesk ticket
    letters = letters_missing_from_sending_bucket(resend_created_notifications_older_than)

    if len(letters) > 0:
        msg = (
            "{} letters were created over an hour ago, "
            "but do not have an updated_at timestamp or billable units. "
            "\n Creating app.celery.letters_pdf_tasks.create_letters tasks to upload letter to S3 "
            "and update notifications for the following notification ids: "
            "\n {}".format(len(letters), [x.id for x in letters])
        )

        current_app.logger.info(msg)
        for letter in letters:
            get_pdf_for_templated_letter.apply_async([str(letter.id)], queue=QueueNames.CREATE_LETTERS_PDF)


@notify_celery.task(name="check-if-letters-still-pending-virus-check")
def check_if_letters_still_pending_virus_check():
    letters = []

    for letter in dao_precompiled_letters_still_pending_virus_check():
        # find letter in the scan bucket
        filename = generate_letter_pdf_filename(
            letter.reference, letter.created_at, ignore_folder=True, postage=letter.postage
        )

        if s3.file_exists(current_app.config["LETTERS_SCAN_BUCKET_NAME"], filename):
            current_app.logger.warning(
                f"Letter id {letter.id} got stuck in pending-virus-check. Sending off for scan again."
            )
            notify_celery.send_task(
                name=TaskNames.SCAN_FILE,
                kwargs={"filename": filename},
                queue=QueueNames.ANTIVIRUS,
            )
        else:
            letters.append(letter)

    if len(letters) > 0:
        letter_ids = [(str(letter.id), letter.reference) for letter in letters]

        msg = f"""{len(letters)} precompiled letters have been pending-virus-check for over 90 minutes.
            We couldn't find them in the scan bucket. We'll need to find out where the files are and kick them off
            again or move them to technical failure.

            Notifications: {sorted(letter_ids)}"""

        if current_app.should_send_zendesk_alerts:
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] Letters still pending virus check",
                message=msg,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
            current_app.logger.error(msg)


@notify_celery.task(name="check-if-letters-still-in-created")
def check_if_letters_still_in_created():
    letters = dao_old_letters_with_created_status()

    if len(letters) > 0:
        msg = (
            "{} letters were created before 17.30 yesterday and still have 'created' status. "
            "Follow runbook to resolve: "
            "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook"
            "#deal-with-Letters-still-in-created.".format(len(letters))
        )

        if current_app.should_send_zendesk_alerts:
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] Letters still in 'created' status",
                message=msg,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
            current_app.logger.error(msg)


@notify_celery.task(name="check-for-missing-rows-in-completed-jobs")
def check_for_missing_rows_in_completed_jobs():
    jobs = find_jobs_with_missing_rows()
    for job in jobs:
        recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)
        missing_rows = find_missing_row_for_job(job.id, job.notification_count)
        for row_to_process in missing_rows:
            row = recipient_csv[row_to_process.missing_row]
            current_app.logger.info("Processing missing row: {} for job: {}".format(row_to_process.missing_row, job.id))
            process_row(row, template, job, job.service, sender_id=sender_id)


@notify_celery.task(name="check-for-services-with-high-failure-rates-or-sending-to-tv-numbers")
def check_for_services_with_high_failure_rates_or_sending_to_tv_numbers():
    start_date = datetime.utcnow() - timedelta(days=1)
    end_date = datetime.utcnow()
    message = ""

    services_with_failures = dao_find_services_with_high_failure_rates(start_date=start_date, end_date=end_date)
    services_sending_to_tv_numbers = dao_find_services_sending_to_tv_numbers(start_date=start_date, end_date=end_date)

    if services_with_failures:
        message += "{} service(s) have had high permanent-failure rates for sms messages in last 24 hours:\n".format(
            len(services_with_failures)
        )
        for service in services_with_failures:
            service_dashboard = "{}/services/{}".format(
                current_app.config["ADMIN_BASE_URL"],
                str(service.service_id),
            )
            message += "service: {} failure rate: {},\n".format(service_dashboard, service.permanent_failure_rate)
    elif services_sending_to_tv_numbers:
        message += "{} service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n".format(
            len(services_sending_to_tv_numbers)
        )
        for service in services_sending_to_tv_numbers:
            service_dashboard = "{}/services/{}".format(
                current_app.config["ADMIN_BASE_URL"],
                str(service.service_id),
            )
            message += "service: {} count of sms to tv numbers: {},\n".format(
                service_dashboard, service.notification_count
            )

    if services_with_failures or services_sending_to_tv_numbers:
        current_app.logger.warning(message)

        if current_app.should_send_zendesk_alerts:
            message += (
                "\nYou can find instructions for this ticket in our manual:\n"
                "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa
            )  # noqa
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] High failure rates for sms spotted for services",
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
            )
            zendesk_client.send_ticket_to_zendesk(ticket)


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


@notify_celery.task(name="zendesk-new-email-branding-report")
def zendesk_new_email_branding_report():
    previous_weekday = datetime.today().date() - timedelta(days=1)

    # If yesterday is a Saturday or Sunday, adjust back to the Friday
    if previous_weekday.isoweekday() in {6, 7}:
        previous_weekday -= timedelta(days=(previous_weekday.isoweekday() - 5))

    new_email_brands = (
        EmailBranding.query.join(Organisation, isouter=True).filter(EmailBranding.created_at >= previous_weekday).all()
    )

    current_app.logger.info(f"{len(new_email_brands)} new email brands to review since {previous_weekday}.")

    if not new_email_brands:
        return

    brands_by_organisation = defaultdict(list)
    brands_with_no_organisation = []
    for new_brand in new_email_brands:
        if not new_brand.organisations:
            brands_with_no_organisation.append(new_brand)

        else:
            for organisation in new_brand.organisations:
                brands_by_organisation[organisation].append(new_brand)

    with open("templates/tasks/scheduled_tasks/new_email_brandings.html") as template_file:
        template = jinja2.Template(template_file.read())

    message = template.render(
        domain=current_app.config["ADMIN_BASE_URL"],
        yesterday=previous_weekday.strftime("%A %-d %B %Y"),
        brands_by_organisation=brands_by_organisation,
        brands_with_no_organisation=brands_with_no_organisation,
    )

    if current_app.should_send_zendesk_alerts:
        ticket = NotifySupportTicket(
            subject="Review new email brandings",
            message=message,
            ticket_type=NotifySupportTicket.TYPE_TASK,
            technical_ticket=False,
            ticket_categories=["notify_no_ticket_category"],
            message_as_html=True,
        )
        zendesk_client.send_ticket_to_zendesk(ticket)


@notify_celery.task(name="check-for-low-available-inbound-sms-numbers")
@cronitor("check-for-low-available-inbound-sms-numbers")
def check_for_low_available_inbound_sms_numbers():
    if not current_app.should_send_zendesk_alerts:
        current_app.logger.info(f"Skipping report run on in {current_app.config['NOTIFY_ENVIRONMENT']}")
        return

    num_available_inbound_numbers = len(dao_get_available_inbound_numbers())
    current_app.logger.info(f"There are {num_available_inbound_numbers} available inbound SMS numbers.")
    if num_available_inbound_numbers > current_app.config["LOW_INBOUND_SMS_NUMBER_THRESHOLD"]:
        return

    message = (
        f"There are only {num_available_inbound_numbers} inbound SMS numbers currently available for services.\n\n"
        "Request more from our provider (MMG) and load them into the database.\n\n"
        "Follow the guidance here: "
        "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Add-new-inbound-SMS-numbers"
    )

    ticket = NotifySupportTicket(
        subject="Request more inbound SMS numbers",
        message=message,
        ticket_type=NotifySupportTicket.TYPE_TASK,
        technical_ticket=True,
        ticket_categories=["notify_no_ticket_category"],
    )
    zendesk_client.send_ticket_to_zendesk(ticket)
