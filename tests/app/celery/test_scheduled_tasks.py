import time
from collections import namedtuple
from datetime import datetime, timedelta
from unittest.mock import call

import pytest
from freezegun import freeze_time

from app.models import BroadcastMessage, BroadcastStatusType, Event, User
from app.tasks import scheduled_tasks
from app.tasks.scheduled_tasks import (
    auto_expire_broadcast_messages,
    delete_invitations,
    delete_old_records_from_events_table,
    delete_verify_codes,
    queue_after_alert_activities,
    remove_yesterdays_planned_tests_on_govuk_alerts,
    trigger_link_tests,
    validate_functional_test_account_emails,
)
from tests.app.db import create_broadcast_message
from tests.conftest import set_config


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch("app.tasks.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago")
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_db_session, mocker):
    mocker.patch("app.tasks.scheduled_tasks.delete_invitations_created_more_than_two_days_ago")
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
    _ = mocker.patch(
        "app.tasks.scheduled_tasks.trigger_link_tests",
    )
    primary_to_A = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_primary_to_A.send")
    primary_to_B = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_primary_to_B.send")
    secondary_to_A = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_secondary_to_A.send")
    secondary_to_B = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_secondary_to_B.send")

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone", "o2", "three"}):
        trigger_link_tests()

    assert primary_to_A.call_count == 4
    assert primary_to_B.call_count == 4
    assert secondary_to_A.call_count == 4
    assert secondary_to_B.call_count == 4

    for cbc_name in ["ee", "vodafone", "o2", "three"]:
        assert call(provider=cbc_name) in primary_to_A.call_args_list
        assert call(provider=cbc_name) in primary_to_B.call_args_list
        assert call(provider=cbc_name) in secondary_to_A.call_args_list
        assert call(provider=cbc_name) in secondary_to_B.call_args_list


def test_trigger_link_tests_calls_for_a_single_provider(mocker, notify_api):
    _ = mocker.patch(
        "app.tasks.scheduled_tasks.trigger_link_tests",
    )
    primary_to_A = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_primary_to_A.send")
    primary_to_B = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_primary_to_B.send")
    secondary_to_A = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_secondary_to_A.send")
    secondary_to_B = mocker.patch("app.tasks.scheduled_tasks.trigger_link_test_secondary_to_B.send")

    with set_config(notify_api, "ENABLED_CBCS", {"ee"}):
        trigger_link_tests()

    assert len(primary_to_A.call_args_list) == 1

    assert call.apply_async(provider="ee") in primary_to_A.call_args_list
    assert call.apply_async(provider="ee") in primary_to_B.call_args_list
    assert call.apply_async(provider="ee") in secondary_to_A.call_args_list
    assert call.apply_async(provider="ee") in secondary_to_B.call_args_list

    assert call.apply_async(provider="o2") not in primary_to_A.call_args_list
    assert call.apply_async(provider="three") not in primary_to_B.call_args_list
    assert call.apply_async(provider="vodafone") not in secondary_to_A.call_args_list
    assert call.apply_async(provider="o2") not in secondary_to_B.call_args_list


def test_trigger_link_does_nothing_if_cbc_proxy_disabled(mocker, notify_api):
    mock_trigger_link_tests = mocker.patch(
        "app.tasks.scheduled_tasks.trigger_link_tests",
    )

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}), set_config(notify_api, "CBC_PROXY_ENABLED", False):
        trigger_link_tests()

    assert mock_trigger_link_tests.called is False


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
    mock_task = mocker.patch("app.tasks.broadcast_message_tasks.publish_govuk_alerts.send")

    auto_expire_broadcast_messages()
    assert message.status == final_status

    assert not mock_task.called


def test_remove_yesterdays_planned_tests_on_govuk_alerts(notify_db_session, mocker):
    mock_task = mocker.patch("app.tasks.broadcast_message_tasks.publish_govuk_alerts.send")

    remove_yesterdays_planned_tests_on_govuk_alerts()

    mock_task.assert_called_once_with()


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
    task_mock = mocker.patch(
        "app.tasks.broadcast_message_tasks.publish_govuk_alerts.send",
    )
    mocker.patch(
        "app.tasks.scheduled_tasks.dao_get_all_finished_broadcast_messages_with_outstanding_actions",
        return_value=[BroadcastMessage(finished_govuk_acknowledged=finished_govuk_acknowledged)],
    )

    queue_after_alert_activities()

    # We expect a publish event if anything returned looked to be pending (i.e. not acknowledged)
    if not finished_govuk_acknowledged:
        task_mock.assert_called_once_with()
    else:
        task_mock.assert_not_called()
