import time
from collections import namedtuple
from datetime import datetime, timedelta
from unittest.mock import call

import pytest
from emergency_alerts_utils.celery import QueueNames, TaskNames
from freezegun import freeze_time

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    auto_expire_broadcast_messages,
    delete_invitations,
    delete_old_records_from_events_table,
    delete_verify_codes,
    remove_yesterdays_planned_tests_on_govuk_alerts,
    trigger_link_tests,
    validate_functional_test_account_emails,
)
from app.models import BroadcastStatusType, Event, User
from tests.app.db import create_broadcast_message
from tests.conftest import set_config


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


def test_trigger_link_tests_calls_for_all_providers(mocker, notify_api):
    mock_trigger_link_test = mocker.patch(
        "app.celery.scheduled_tasks.trigger_link_test",
    )

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}):
        trigger_link_tests()

    args = mock_trigger_link_test.apply_async.call_args_list
    assert call(kwargs={"provider": "ee"}, queue="broadcast-tasks") in args
    assert call(kwargs={"provider": "vodafone"}, queue="broadcast-tasks") in args


def test_trigger_link_does_nothing_if_cbc_proxy_disabled(mocker, notify_api):
    mock_trigger_link_test = mocker.patch(
        "app.celery.scheduled_tasks.trigger_link_test",
    )

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}), set_config(notify_api, "CBC_PROXY_ENABLED", False):
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
