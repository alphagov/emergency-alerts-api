import builtins
import time
from collections import namedtuple
from datetime import datetime, timedelta
from unittest.mock import mock_open, patch

import boto3
import pytest
from emergency_alerts_utils.celery import QueueNames, TaskNames
from flask import current_app
from freezegun import freeze_time
from moto import mock_aws

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (  # trigger_link_tests,
    auto_expire_broadcast_messages,
    delete_invitations,
    delete_old_records_from_events_table,
    delete_verify_codes,
    queue_after_alert_activities,
    remove_yesterdays_planned_tests_on_govuk_alerts,
    run_health_check,
    validate_functional_test_account_emails,
)
from app.models import BroadcastMessage, BroadcastStatusType, Event, User
from tests.app.db import create_broadcast_message
from tests.conftest import set_config

# from unittest.mock import call


# from tests.conftest import set_config


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch("app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago")
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_db_session, mocker):
    mocker.patch("app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago")
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


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


# def test_trigger_link_tests_calls_for_all_providers(mocker, notify_api):
#     mock_trigger_link_test = mocker.patch(
#         "app.celery.scheduled_tasks.trigger_link_test",
#     )

#     with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}):
#         trigger_link_tests()

#     args = mock_trigger_link_test.apply_async.call_args_list
#     assert call(kwargs={"provider": "ee"}, queue="broadcast-tasks") in args
#     assert call(kwargs={"provider": "vodafone"}, queue="broadcast-tasks") in args


# def test_trigger_link_does_nothing_if_cbc_proxy_disabled(mocker, notify_api):
#     mock_trigger_link_test = mocker.patch(
#         "app.celery.scheduled_tasks.trigger_link_test",
#     )

#     with set_config(
#         notify_api, "ENABLED_CBCS", {"ee", "vodafone"}
#     ), set_config(notify_api, "CBC_PROXY_ENABLED", False):
#         trigger_link_tests()

#     assert mock_trigger_link_test.called is False


@freeze_time("2021-07-19 15:50")
@pytest.mark.parametrize(
    "status, finishes_at, final_status",
    [
        (BroadcastStatusType.BROADCASTING, "2021-07-19 16:00", BroadcastStatusType.BROADCASTING),
        (BroadcastStatusType.BROADCASTING, "2021-07-19 15:40", BroadcastStatusType.COMPLETED),
        (BroadcastStatusType.BROADCASTING, None, BroadcastStatusType.BROADCASTING),
        (BroadcastStatusType.PENDING_APPROVAL, None, BroadcastStatusType.PENDING_APPROVAL),
        (BroadcastStatusType.CANCELLED, "2021-07-19 15:40", BroadcastStatusType.CANCELLED),
    ],
)
def test_auto_expire_broadcast_messages(
    mocker,
    status,
    finishes_at,
    final_status,
    sample_template,
):
    message = create_broadcast_message(
        status=status,
        finishes_at=finishes_at,
        template=sample_template,
    )
    mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")

    auto_expire_broadcast_messages()
    assert message.status == final_status

    assert not mock_celery.called


def test_remove_yesterdays_planned_tests_on_govuk_alerts(mocker):
    mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")

    remove_yesterdays_planned_tests_on_govuk_alerts()

    mock_celery.assert_called_once_with(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)


def test_delete_old_records_from_events_table(notify_db_session):
    old_datetime, recent_datetime = datetime.now() - timedelta(weeks=78), datetime.now() - timedelta(weeks=50)
    old_event = Event(event_type="test_event", created_at=old_datetime, data={})
    recent_event = Event(event_type="test_event", created_at=recent_datetime, data={})

    notify_db_session.add(old_event)
    notify_db_session.add(recent_event)
    notify_db_session.commit()

    delete_old_records_from_events_table()

    events = Event.query.filter(Event.event_type == "test_event").all()
    assert len(events) == 1
    assert events[0].created_at == recent_datetime


def test_validate_functional_test_account_emails(notify_db_session):
    user1 = User(
        name="Test User 1",
        email_address="emergency-alerts-tests+user1@digital.cabinet-office.gov.uk",
        password="password",
        auth_type="sms_auth",
        mobile_number="07700900000",
    )
    user2 = User(
        name="Test User 2",
        email_address="emergency-alerts-tests+user2@digital.cabinet-office.gov.uk",
        password="password",
        auth_type="sms_auth",
        mobile_number="07700900000",
    )

    notify_db_session.add(user1)
    notify_db_session.add(user2)
    notify_db_session.commit()

    now = datetime.now()
    time.sleep(1)

    validate_functional_test_account_emails()

    users = User.query.filter(User.email_address.ilike("emergency-alerts-tests%")).all()

    assert users[0].email_access_validated_at > now
    assert users[1].email_access_validated_at > now


@pytest.mark.parametrize(
    "finished_govuk_acknowledged",
    (True, False),
)
def test_queue_after_alert_activities_does_govuk_refresh(notify_api, mocker, finished_govuk_acknowledged):
    celery_mock = mocker.patch(
        "app.notify_celery.send_task",
    )
    mocker.patch(
        "app.celery.scheduled_tasks.dao_get_all_finished_broadcast_messages_with_outstanding_actions",
        return_value=[BroadcastMessage(finished_govuk_acknowledged=finished_govuk_acknowledged)],
    )

    queue_after_alert_activities()

    # We expect a publish event if anything returned looked to be pending (i.e. not acknowledged)
    if not finished_govuk_acknowledged:
        celery_mock.assert_called_once_with(name=TaskNames.PUBLISH_GOVUK_ALERTS, queue=QueueNames.GOVUK_ALERTS)
    else:
        celery_mock.assert_not_called()


# Mock only open() for the healthcheck path, but allow others (botocore) to read
# normally for its internal init logic
def open_for_healthcheck(original_open):
    def side_effect(*args, **kwargs):
        if args[0] == "/eas/emergency-alerts-api/celery-beat-healthcheck":
            return mock_open()()
        return original_open(*args, **kwargs)

    return side_effect


@mock_aws
def test_celery_healthcheck_posts_to_cloudwatch(mocker, notify_api):
    with patch.object(builtins, "open", side_effect=open_for_healthcheck(open)):
        with set_config(notify_api, "SERVICE", "celery"):
            run_health_check()

    cloudwatch = boto3.client("cloudwatch", region_name=current_app.config["AWS_REGION"])
    metric = cloudwatch.list_metrics()["Metrics"][0]
    assert metric["MetricName"] == "AppVersion"
    assert metric["Namespace"] == "Emergency Alerts"
    assert {"Name": "Application", "Value": "celery"} in metric["Dimensions"]
