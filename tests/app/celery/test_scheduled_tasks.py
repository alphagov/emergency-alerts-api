# import uuid
from collections import namedtuple
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import call

import pytest

# from emergency_alerts_utils.clients.zendesk.zendesk_client import (
#     NotifySupportTicket,
# )
from freezegun import freeze_time

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    auto_expire_broadcast_messages,
    check_for_missing_rows_in_completed_jobs,
    check_job_status,
    delete_invitations,
    delete_old_records_from_events_table,
    delete_verify_codes,
    remove_yesterdays_planned_tests_on_govuk_alerts,
    run_scheduled_jobs,
    trigger_link_tests,
)
from app.config import QueueNames, TaskNames
from app.dao.jobs_dao import dao_get_job_by_id

# from app.dao.provider_details_dao import get_provider_details_by_identifier
from app.models import (
    JOB_STATUS_ERROR,
    JOB_STATUS_FINISHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    BroadcastStatusType,
    Event,
)
from tests.app import load_example_csv
from tests.app.db import (
    create_broadcast_message,
    create_job,
    create_notification,
)
from tests.conftest import set_config


def _create_slow_delivery_notification(template, provider="mmg"):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)

    create_notification(
        template=template,
        status="delivered",
        sent_by=provider,
        updated_at=five_minutes_from_now,
        sent_at=now,
    )


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch("app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago")
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_db_session, mocker):
    mocker.patch("app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago")
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


def test_should_update_scheduled_jobs_and_put_on_queue(mocker, sample_template):
    mocked = mocker.patch("app.celery.tasks.process_job.apply_async")

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    job = create_job(sample_template, job_status="scheduled", scheduled_for=one_minute_in_the_past)

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == "pending"
    mocked.assert_called_with([str(job.id)], queue="job-tasks")


def test_should_update_all_scheduled_jobs_and_put_on_queue(sample_template, mocker):
    mocked = mocker.patch("app.celery.tasks.process_job.apply_async")

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    ten_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=10)
    twenty_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=20)
    job_1 = create_job(sample_template, job_status="scheduled", scheduled_for=one_minute_in_the_past)
    job_2 = create_job(sample_template, job_status="scheduled", scheduled_for=ten_minutes_in_the_past)
    job_3 = create_job(sample_template, job_status="scheduled", scheduled_for=twenty_minutes_in_the_past)

    run_scheduled_jobs()

    assert dao_get_job_by_id(job_1.id).job_status == "pending"
    assert dao_get_job_by_id(job_2.id).job_status == "pending"
    assert dao_get_job_by_id(job_2.id).job_status == "pending"

    mocked.assert_has_calls(
        [
            call([str(job_3.id)], queue="job-tasks"),
            call([str(job_2.id)], queue="job-tasks"),
            call([str(job_1.id)], queue="job-tasks"),
        ]
    )


# @freeze_time("2017-05-01 14:00:00")
# def test_switch_current_sms_provider_on_slow_delivery_switches_when_one_provider_is_slow(
#     mocker,
#     restore_provider_details,
# ):
#     is_slow_dict = {"mmg": False, "firetext": True}
#     mock_is_slow = mocker.patch("app.celery.scheduled_tasks.is_delivery_slow_for_providers", return_value=is_slow_dict)  # noqa
#     mock_reduce = mocker.patch("app.celery.scheduled_tasks.dao_reduce_sms_provider_priority")
#     # updated_at times are older than the 10 minute window
#     get_provider_details_by_identifier("mmg").updated_at = datetime(2017, 5, 1, 13, 49)
#     get_provider_details_by_identifier("firetext").updated_at = None

#     switch_current_sms_provider_on_slow_delivery()

#     mock_is_slow.assert_called_once_with(
#         threshold=0.3, created_at=datetime(2017, 5, 1, 13, 50), delivery_time=timedelta(minutes=4)
#     )
#     mock_reduce.assert_called_once_with("firetext", time_threshold=timedelta(minutes=10))


# @freeze_time("2017-05-01 14:00:00")
# @pytest.mark.parametrize(
#     "is_slow_dict",
#     [
#         {"mmg": False, "firetext": False},
#         {"mmg": True, "firetext": True},
#     ],
# )
# def test_switch_current_sms_provider_on_slow_delivery_does_nothing_if_no_need(
#     mocker, restore_provider_details, is_slow_dict
# ):
#     mocker.patch("app.celery.scheduled_tasks.is_delivery_slow_for_providers", return_value=is_slow_dict)
#     mock_reduce = mocker.patch("app.celery.scheduled_tasks.dao_reduce_sms_provider_priority")
#     get_provider_details_by_identifier("mmg").updated_at = datetime(2017, 5, 1, 13, 51)

#     switch_current_sms_provider_on_slow_delivery()

#     assert mock_reduce.called is False


def test_check_job_status_task_calls_process_incomplete_jobs(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_notification(template=sample_template, job=job)
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_calls_process_incomplete_jobs_when_scheduled_job_is_not_complete(
    mocker, sample_template
):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_calls_process_incomplete_jobs_for_pending_scheduled_jobs(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_PENDING,
    )

    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_does_not_call_process_incomplete_jobs_for_non_scheduled_pending_jobs(
    mocker,
    sample_template,
):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        job_status=JOB_STATUS_PENDING,
    )
    check_job_status()

    assert not mock_celery.called


def test_check_job_status_task_calls_process_incomplete_jobs_for_multiple_jobs(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id), str(job_2.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_only_sends_old_tasks(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=50),
        scheduled_for=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_PENDING,
    )
    check_job_status()

    # jobs 2 and 3 were created less than 30 minutes ago, so are not sent to Celery task
    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_sets_jobs_to_error(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    check_job_status()

    # job 2 not in celery task
    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)
    assert job.job_status == JOB_STATUS_ERROR
    assert job_2.job_status == JOB_STATUS_IN_PROGRESS


# def test_replay_created_notifications(notify_db_session, sample_service, mocker):
#     email_delivery_queue = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
#     sms_delivery_queue = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

#     sms_template = create_template(service=sample_service, template_type="sms")
#     email_template = create_template(service=sample_service, template_type="email")
#     older_than = (60 * 60) + (60 * 15)  # 1 hour 15 minutes
#     # notifications expected to be resent
#     old_sms = create_notification(
#         template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="created"
#     )
#     old_email = create_notification(
#         template=email_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="created"
#     )
#     # notifications that are not to be resent
#     create_notification(
#         template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="sending"
#     )
#     create_notification(
#         template=email_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="delivered"
#     )
#     create_notification(template=sms_template, created_at=datetime.utcnow(), status="created")
#     create_notification(template=email_template, created_at=datetime.utcnow(), status="created")

#     replay_created_notifications()
#     email_delivery_queue.assert_called_once_with([str(old_email.id)], queue="send-email-tasks")
#     sms_delivery_queue.assert_called_once_with([str(old_sms.id)], queue="send-sms-tasks")


# def test_replay_created_notifications_get_pdf_for_templated_letter_tasks_for_letters_not_ready_to_send(
#     sample_letter_template, mocker
# ):
#     mock_task = mocker.patch("app.celery.scheduled_tasks.get_pdf_for_templated_letter.apply_async")
#     create_notification(
#         template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(hours=4)
#     )

#     create_notification(
#         template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(minutes=20)
#     )
#     notification_1 = create_notification(
#         template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(hours=1, minutes=20)  # noqa
#     )
#     notification_2 = create_notification(
#         template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(hours=5)
#     )

#     replay_created_notifications()

#     calls = [
#         call([str(notification_1.id)], queue=QueueNames.CREATE_LETTERS_PDF),
#         call([str(notification_2.id)], queue=QueueNames.CREATE_LETTERS_PDF),
#     ]
#     mock_task.assert_has_calls(calls, any_order=True)


def test_check_job_status_task_does_not_raise_error(sample_template):
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED,
    )

    check_job_status()


# @freeze_time("2019-05-30 14:00:00")
# def test_check_if_letters_still_pending_virus_check_restarts_scan_for_stuck_letters(mocker, sample_letter_template):
#     mock_file_exists = mocker.patch("app.aws.s3.file_exists", return_value=True)
#     mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
#     mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")

#     create_notification(
#         template=sample_letter_template,
#         status=NOTIFICATION_PENDING_VIRUS_CHECK,
#         created_at=datetime.utcnow() - timedelta(seconds=5401),
#         reference="one",
#     )
#     expected_filename = "NOTIFY.ONE.D.2.C.20190530122959.PDF"

#     check_if_letters_still_pending_virus_check()

#     mock_file_exists.assert_called_once_with("test-letters-scan", expected_filename)

#     mock_celery.assert_called_once_with(
#         name=TaskNames.SCAN_FILE, kwargs={"filename": expected_filename}, queue=QueueNames.ANTIVIRUS
#     )

#     assert mock_create_ticket.called is False


# @freeze_time("2019-05-30 14:00:00")
# def test_check_if_letters_still_pending_virus_check_raises_zendesk_if_files_cant_be_found(
#     mocker, sample_letter_template
# ):
#     mock_file_exists = mocker.patch("app.aws.s3.file_exists", return_value=False)
#     mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
#     mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")
#     mock_send_ticket_to_zendesk = mocker.patch(
#         "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
#         autospec=True,
#     )

#     create_notification(
#         template=sample_letter_template,
#         status=NOTIFICATION_PENDING_VIRUS_CHECK,
#         created_at=datetime.utcnow() - timedelta(seconds=5400),
#     )
#     create_notification(
#         template=sample_letter_template,
#         status=NOTIFICATION_DELIVERED,
#         created_at=datetime.utcnow() - timedelta(seconds=6000),
#     )
#     notification_1 = create_notification(
#         template=sample_letter_template,
#         status=NOTIFICATION_PENDING_VIRUS_CHECK,
#         created_at=datetime.utcnow() - timedelta(seconds=5401),
#         reference="one",
#     )
#     notification_2 = create_notification(
#         template=sample_letter_template,
#         status=NOTIFICATION_PENDING_VIRUS_CHECK,
#         created_at=datetime.utcnow() - timedelta(seconds=70000),
#         reference="two",
#     )

#     check_if_letters_still_pending_virus_check()

#     assert mock_file_exists.call_count == 2
#     mock_file_exists.assert_has_calls(
#         [
#             call("test-letters-scan", "NOTIFY.ONE.D.2.C.20190530122959.PDF"),
#             call("test-letters-scan", "NOTIFY.TWO.D.2.C.20190529183320.PDF"),
#         ],
#         any_order=True,
#     )
#     assert mock_celery.called is False

#     mock_create_ticket.assert_called_once_with(
#         ANY,
#         subject="[test] Letters still pending virus check",
#         message=ANY,
#         ticket_type="incident",
#         technical_ticket=True,
#         ticket_categories=["notify_letters"],
#     )
#     assert "2 precompiled letters have been pending-virus-check" in mock_create_ticket.call_args.kwargs["message"]
#     assert f"{(str(notification_1.id), notification_1.reference)}" in mock_create_ticket.call_args.kwargs["message"]
#     assert f"{(str(notification_2.id), notification_2.reference)}" in mock_create_ticket.call_args.kwargs["message"]
#     mock_send_ticket_to_zendesk.assert_called_once()


# @freeze_time("2019-05-30 14:00:00")
# def test_check_if_letters_still_in_created_during_bst(mocker, sample_letter_template):
#     mock_logger = mocker.patch("app.celery.tasks.current_app.logger.error")
#     mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
#     mock_send_ticket_to_zendesk = mocker.patch(
#         "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
#         autospec=True,
#     )

#     create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 1, 12, 0))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 29))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 30))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 17, 29))
#     create_notification(template=sample_letter_template, status="delivered", created_at=datetime(2019, 5, 28, 10, 0))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 30, 10, 0))

#     check_if_letters_still_in_created()

#     message = (
#         "2 letters were created before 17.30 yesterday and still have 'created' status. "
#         "Follow runbook to resolve: "
#         "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-Letters-still-in-created."
#     )

#     mock_logger.assert_called_once_with(message)
#     mock_create_ticket.assert_called_with(
#         ANY,
#         message=message,
#         subject="[test] Letters still in 'created' status",
#         ticket_type="incident",
#         technical_ticket=True,
#         ticket_categories=["notify_letters"],
#     )
#     mock_send_ticket_to_zendesk.assert_called_once()


# @freeze_time("2019-01-30 14:00:00")
# def test_check_if_letters_still_in_created_during_utc(mocker, sample_letter_template):
#     mock_logger = mocker.patch("app.celery.tasks.current_app.logger.error")
#     mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
#     mock_send_ticket_to_zendesk = mocker.patch(
#         "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
#         autospec=True,
#     )

#     create_notification(template=sample_letter_template, created_at=datetime(2018, 12, 1, 12, 0))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 29))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 30))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 18, 29))
#     create_notification(template=sample_letter_template, status="delivered", created_at=datetime(2019, 1, 29, 10, 0))
#     create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 30, 10, 0))

#     check_if_letters_still_in_created()

#     message = (
#         "2 letters were created before 17.30 yesterday and still have 'created' status. "
#         "Follow runbook to resolve: "
#         "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-Letters-still-in-created."
#     )

#     mock_logger.assert_called_once_with(message)
#     mock_create_ticket.assert_called_once_with(
#         ANY,
#         message=message,
#         subject="[test] Letters still in 'created' status",
#         ticket_type="incident",
#         technical_ticket=True,
#         ticket_categories=["notify_letters"],
#     )
#     mock_send_ticket_to_zendesk.assert_called_once()


@pytest.mark.parametrize(
    "offset",
    (
        timedelta(days=1),
        pytest.param(timedelta(hours=23, minutes=59), marks=pytest.mark.xfail),
        pytest.param(timedelta(minutes=20), marks=pytest.mark.xfail),
        timedelta(minutes=19),
    ),
)
def test_check_for_missing_rows_in_completed_jobs_ignores_old_and_new_jobs(
    mocker,
    sample_email_template,
    offset,
):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.encryption.encrypt", return_value="something_encrypted")
    process_row = mocker.patch("app.celery.scheduled_tasks.process_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - offset,
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    assert process_row.called is False


def test_check_for_missing_rows_in_completed_jobs(mocker, sample_email_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.encryption.encrypt", return_value="something_encrypted")
    process_row = mocker.patch("app.celery.scheduled_tasks.process_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    process_row.assert_called_once_with(mock.ANY, mock.ANY, job, job.service, sender_id=None)


def test_check_for_missing_rows_in_completed_jobs_calls_save_email(mocker, sample_email_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    save_email_task = mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.encryption.encrypt", return_value="something_encrypted")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    save_email_task.assert_called_once_with(
        (
            str(job.service_id),
            "uuid",
            "something_encrypted",
        ),
        {},
        queue="database-tasks",
    )


def test_check_for_missing_rows_in_completed_jobs_uses_sender_id(mocker, sample_email_template, fake_uuid):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": fake_uuid}),
    )
    mock_process_row = mocker.patch("app.celery.scheduled_tasks.process_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    mock_process_row.assert_called_once_with(mock.ANY, mock.ANY, job, job.service, sender_id=fake_uuid)


MockServicesSendingToTVNumbers = namedtuple(
    "ServicesSendingToTVNumbers",
    [
        "service_id",
        "notification_count",
    ],
)
MockServicesWithHighFailureRate = namedtuple(
    "ServicesWithHighFailureRate",
    [
        "service_id",
        "permanent_failure_rate",
    ],
)


# @pytest.mark.parametrize(
#     "failure_rates, sms_to_tv_numbers, expected_message",
#     [
#         [
#             [MockServicesWithHighFailureRate("123", 0.3)],
#             [],
#             "1 service(s) have had high permanent-failure rates for sms messages in last "
#             "24 hours:\nservice: {}/services/{} failure rate: 0.3,\n".format(Config.ADMIN_BASE_URL, "123"),
#         ],
#         [
#             [],
#             [MockServicesSendingToTVNumbers("123", 300)],
#             "1 service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n"
#             "service: {}/services/{} count of sms to tv numbers: 300,\n".format(Config.ADMIN_BASE_URL, "123"),
#         ],
#     ],
# )
# def test_check_for_services_with_high_failure_rates_or_sending_to_tv_numbers(
#     mocker, notify_db_session, failure_rates, sms_to_tv_numbers, expected_message
# ):
#     mock_logger = mocker.patch("app.celery.tasks.current_app.logger.warning")
#     mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
#     mock_send_ticket_to_zendesk = mocker.patch(
#         "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
#         autospec=True,
#     )
#     mock_failure_rates = mocker.patch(
#         "app.celery.scheduled_tasks.dao_find_services_with_high_failure_rates", return_value=failure_rates
#     )
#     mock_sms_to_tv_numbers = mocker.patch(
#         "app.celery.scheduled_tasks.dao_find_services_sending_to_tv_numbers", return_value=sms_to_tv_numbers
#     )

#     zendesk_actions = "\nYou can find instructions for this ticket in our manual:\nhttps://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa

#     check_for_services_with_high_failure_rates_or_sending_to_tv_numbers()

#     assert mock_failure_rates.called
#     assert mock_sms_to_tv_numbers.called
#     mock_logger.assert_called_once_with(expected_message)
#     mock_create_ticket.assert_called_with(
#         ANY,
#         message=expected_message + zendesk_actions,
#         subject="[test] High failure rates for sms spotted for services",
#         ticket_type="incident",
#         technical_ticket=True,
#     )
#     mock_send_ticket_to_zendesk.assert_called_once()


def test_trigger_link_tests_calls_for_all_providers(mocker, notify_api):
    mock_trigger_link_test = mocker.patch(
        "app.celery.scheduled_tasks.trigger_link_test",
    )

    with set_config(notify_api, "ENABLED_CBCS", ["ee", "vodafone"]):
        trigger_link_tests()

    assert mock_trigger_link_test.apply_async.call_args_list == [
        call(kwargs={"provider": "ee"}, queue="broadcast-tasks"),
        call(kwargs={"provider": "vodafone"}, queue="broadcast-tasks"),
    ]


def test_trigger_link_does_nothing_if_cbc_proxy_disabled(mocker, notify_api):
    mock_trigger_link_test = mocker.patch(
        "app.celery.scheduled_tasks.trigger_link_test",
    )

    with set_config(notify_api, "ENABLED_CBCS", ["ee", "vodafone"]), set_config(notify_api, "CBC_PROXY_ENABLED", False):
        trigger_link_tests()

    assert mock_trigger_link_test.called is False


@freeze_time("2021-07-19 15:50")
@pytest.mark.parametrize(
    "status, finishes_at, final_status, should_call_publish_task",
    [
        (BroadcastStatusType.BROADCASTING, "2021-07-19 16:00", BroadcastStatusType.BROADCASTING, False),
        (BroadcastStatusType.BROADCASTING, "2021-07-19 15:40", BroadcastStatusType.COMPLETED, True),
        (BroadcastStatusType.BROADCASTING, None, BroadcastStatusType.BROADCASTING, False),
        (BroadcastStatusType.PENDING_APPROVAL, None, BroadcastStatusType.PENDING_APPROVAL, False),
        (BroadcastStatusType.CANCELLED, "2021-07-19 15:40", BroadcastStatusType.CANCELLED, False),
    ],
)
def test_auto_expire_broadcast_messages(
    mocker,
    status,
    finishes_at,
    final_status,
    sample_template,
    should_call_publish_task,
):
    message = create_broadcast_message(
        status=status,
        finishes_at=finishes_at,
        template=sample_template,
    )
    mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")

    auto_expire_broadcast_messages()
    assert message.status == final_status

    if should_call_publish_task:
        mock_celery.assert_called_once_with(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)
    else:
        assert not mock_celery.called


def test_remove_yesterdays_planned_tests_on_govuk_alerts(mocker):
    mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")

    remove_yesterdays_planned_tests_on_govuk_alerts()

    mock_celery.assert_called_once_with(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)


def test_delete_old_records_from_events_table(notify_db_session):
    old_datetime, recent_datetime = datetime.utcnow() - timedelta(weeks=78), datetime.utcnow() - timedelta(weeks=50)
    old_event = Event(event_type="test_event", created_at=old_datetime, data={})
    recent_event = Event(event_type="test_event", created_at=recent_datetime, data={})

    notify_db_session.add(old_event)
    notify_db_session.add(recent_event)
    notify_db_session.commit()

    delete_old_records_from_events_table()

    events = Event.query.filter(Event.event_type == "test_event").all()
    assert len(events) == 1
    assert events[0].created_at == recent_datetime


# @freeze_time("2022-11-01 00:30:00")
# def test_zendesk_new_email_branding_report(notify_db_session, mocker):
#     org_1 = create_organisation(organisation_id=uuid.UUID("113d51e7-f204-44d0-99c6-020f3542a527"), name="org-1")
#     org_2 = create_organisation(organisation_id=uuid.UUID("d6bc2309-9f79-4779-b864-46c2892db90e"), name="org-2")
#     email_brand_1 = create_email_branding(id=uuid.UUID("bc5b45e0-af3c-4e3d-a14c-253a56b77480"), name="brand-1")
#     email_brand_2 = create_email_branding(id=uuid.UUID("c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0"), name="brand-2")
#     create_email_branding(id=uuid.UUID("1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e"), name="brand-3")
#     org_1.email_branding_pool = [email_brand_1, email_brand_2]
#     org_2.email_branding_pool = [email_brand_2]
#     org_2.email_branding = email_brand_1
#     notify_db_session.commit()

#     mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

#     zendesk_new_email_branding_report()

#     assert mock_send_ticket.call_count == 1

#     ticket = mock_send_ticket.call_args_list[0][0][0]

#     assert ticket.request_data == {
#         "ticket": {
#             "subject": "Review new email brandings",
#             "comment": {
#                 "html_body": mocker.ANY,
#                 "public": True,
#             },
#             "group_id": 360000036529,
#             "organization_id": 21891972,
#             "ticket_form_id": 1900000284794,
#             "priority": "normal",
#             "tags": ["govuk_notify_support"],
#             "type": "task",
#             "custom_fields": [
#                 {"id": "1900000744994", "value": "notify_ticket_type_non_technical"},
#                 {"id": "360022836500", "value": ["notify_no_ticket_category"]},
#                 {"id": "360022943959", "value": None},
#                 {"id": "360022943979", "value": None},
#                 {"id": "1900000745014", "value": None},
#             ],
#         }
#     }

#     for expected_html_fragment in (
#         "<h2>New email branding to review</h2>\n<p>Uploaded since Monday 31 October 2022:</p>",
#         (
#             "<p>"
#             '<a href="http://localhost:6012/organisations/'
#             '113d51e7-f204-44d0-99c6-020f3542a527/settings/email-branding">org-1</a> (no default):'
#             "</p>"
#             "<ul>"
#             "<li>"
#             '<a href="http://localhost:6012/email-branding/bc5b45e0-af3c-4e3d-a14c-253a56b77480/edit">brand-1</a>'
#             "</li>"
#             "<li>"
#             '<a href="http://localhost:6012/email-branding/c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0/edit">brand-2</a>'
#             "</li>"
#             "</ul>"
#             "<hr>"
#             "<p>"
#             '<a href="http://localhost:6012/organisations/'
#             'd6bc2309-9f79-4779-b864-46c2892db90e/settings/email-branding">org-2</a>:'
#             "</p>"
#             "<ul>"
#             "<li>"
#             '<a href="http://localhost:6012/email-branding/c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0/edit">brand-2</a>'
#             "</li>"
#             "</ul>"
#         ),
#         (
#             "<p>These new brands are not associated with any organisation and do not need reviewing:</p>"
#             "<ul>"
#             "<li>"
#             '<a href="http://localhost:6012/email-branding/1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e/edit">brand-3</a>'
#             "</li>"
#             "</ul>"
#         ),
#     ):
#         assert expected_html_fragment in ticket.request_data["ticket"]["comment"]["html_body"]


# @freeze_time("2022-11-01 00:30:00")
# def test_zendesk_new_email_branding_report_for_unassigned_branding_only(notify_db_session, mocker):
#     create_organisation(organisation_id=uuid.UUID("113d51e7-f204-44d0-99c6-020f3542a527"), name="org-1")
#     create_organisation(organisation_id=uuid.UUID("d6bc2309-9f79-4779-b864-46c2892db90e"), name="org-2")
#     create_email_branding(id=uuid.UUID("bc5b45e0-af3c-4e3d-a14c-253a56b77480"), name="brand-1")
#     create_email_branding(id=uuid.UUID("c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0"), name="brand-2")
#     create_email_branding(id=uuid.UUID("1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e"), name="brand-3")
#     notify_db_session.commit()

#     mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

#     zendesk_new_email_branding_report()

#     assert mock_send_ticket.call_args_list[0][0][0].request_data["ticket"]["comment"]["html_body"] == (
#         "<p>These new brands are not associated with any organisation and do not need reviewing:</p>"
#         "<ul>"
#         "<li>"
#         '<a href="http://localhost:6012/email-branding/bc5b45e0-af3c-4e3d-a14c-253a56b77480/edit">brand-1</a>'
#         "</li><li>"
#         '<a href="http://localhost:6012/email-branding/c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0/edit">brand-2</a>'
#         "</li><li>"
#         '<a href="http://localhost:6012/email-branding/1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e/edit">brand-3</a>'
#         "</li>"
#         "</ul>"
#     )


# @pytest.mark.parametrize(
#     "freeze_datetime, expected_last_day_string",
#     (
#         ("2022-11-20 00:30:00", "Friday 18 November 2022"),
#         ("2022-11-19 00:30:00", "Friday 18 November 2022"),
#         ("2022-11-18 00:30:00", "Thursday 17 November 2022"),
#         ("2022-11-17 00:30:00", "Wednesday 16 November 2022"),
#         ("2022-11-16 00:30:00", "Tuesday 15 November 2022"),
#         ("2022-11-15 00:30:00", "Monday 14 November 2022"),
#         ("2022-11-14 00:30:00", "Friday 11 November 2022"),
#     ),
# )
# def test_zendesk_new_email_branding_report_calculates_last_weekday_correctly(
#     notify_db_session, mocker, freeze_datetime, expected_last_day_string
# ):
#     org_1 = create_organisation(organisation_id=uuid.UUID("113d51e7-f204-44d0-99c6-020f3542a527"), name="org-1")
#     email_brand_1 = create_email_branding(id=uuid.UUID("bc5b45e0-af3c-4e3d-a14c-253a56b77480"), name="brand-1")
#     org_1.email_branding_pool = [email_brand_1]
#     notify_db_session.commit()

#     mocker.patch("app.celery.scheduled_tasks.NotifySupportTicket", wraps=NotifySupportTicket)
#     mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

#     with freeze_time(freeze_datetime):
#         zendesk_new_email_branding_report()

#     # Make sure we've built a NotifySupportTicket with the expected params, and passed that ticket to the zendesk client  # noqa
#     assert expected_last_day_string in mock_send_ticket.call_args_list[0][0][0].message


# def test_zendesk_new_email_branding_report_does_not_create_ticket_if_no_new_brands(notify_db_session, mocker):
#     mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")
#     zendesk_new_email_branding_report()
#     assert mock_send_ticket.call_args_list == []


# def test_check_for_low_available_inbound_sms_numbers_logs_zendesk_ticket_if_too_few_numbers(
#     notify_api, notify_db_session, mocker
# ):
#     mocker.patch(
#         "app.celery.scheduled_tasks.dao_get_available_inbound_numbers",
#         return_value=[InboundNumber() for _ in range(5)],
#     )
#     mock_ticket = mocker.patch("app.celery.scheduled_tasks.NotifySupportTicket")
#     mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

#     with set_config(notify_api, "LOW_INBOUND_SMS_NUMBER_THRESHOLD", 10):
#         check_for_low_available_inbound_sms_numbers()

#     # Make sure we've built a NotifySupportTicket with the expected params, and passed that ticket to the zendesk client  # noqa
#     assert mock_ticket.call_args_list == [
#         mocker.call(
#             subject="Request more inbound SMS numbers",
#             message=(
#                 "There are only 5 inbound SMS numbers currently available for services.\n\n"
#                 "Request more from our provider (MMG) and load them into the database.\n\n"
#                 "Follow the guidance here: "
#                 "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Add-new-inbound-SMS-numbers"
#             ),
#             ticket_type=mock_ticket.TYPE_TASK,
#             technical_ticket=True,
#             ticket_categories=["notify_no_ticket_category"],
#         )
#     ]
#     assert mock_send_ticket.call_args_list == [mocker.call(mock_ticket.return_value)]


# def test_check_for_low_available_inbound_sms_numbers_does_not_proceed_if_enough_numbers(
#     notify_api, notify_db_session, mocker
# ):
#     mocker.patch(
#         "app.celery.scheduled_tasks.dao_get_available_inbound_numbers",
#         return_value=[InboundNumber() for _ in range(11)],
#     )
#     mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

#     with set_config(notify_api, "LOW_INBOUND_SMS_NUMBER_THRESHOLD", 10):
#         check_for_low_available_inbound_sms_numbers()

#     assert mock_send_ticket.call_args_list == []
