import time
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, call

import pytest
from emergency_alerts_utils.clients.slack.slack_client import SlackError
from freezegun import freeze_time

from app import db
from app.models import BroadcastMessage, BroadcastStatusType, Event, User
from app.tasks import scheduled_tasks
from app.tasks.scheduled_tasks import (
    auto_expire_broadcast_messages,
    check_api_key_expiry,
    delete_invitations,
    delete_old_records_from_events_table,
    delete_verify_codes,
    purge_functional_test_alerts,
    queue_after_alert_activities,
    remove_yesterdays_planned_tests_on_govuk_alerts,
    trigger_link_tests,
    validate_functional_test_account_emails,
)
from tests.app.db import (
    create_api_key,
    create_broadcast_message,
    create_service,
)
from tests.conftest import set_config, set_config_values


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
    mock_task = mocker.patch("app.tasks.scheduled_tasks.publish_govuk_build")

    auto_expire_broadcast_messages()
    assert message.status == final_status

    assert not mock_task.called


def test_remove_yesterdays_planned_tests_on_govuk_alerts(notify_db_session, mocker):
    mock_task = mocker.patch("app.tasks.scheduled_tasks.publish_govuk_build_full", return_value=(Mock(), Mock()))

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

    # UTC datetime but email_access_validated_at is offset-naive so remove TZ info
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    time.sleep(1)

    validate_functional_test_account_emails()

    users = User.query.filter(User.email_address.ilike("emergency-alerts-tests%")).all()

    assert users[0].email_access_validated_at > now
    assert users[1].email_access_validated_at > now


def test_purge_functional_test_alerts_calls_util(notify_api, mocker):
    mocked_purge = mocker.patch("app.tasks.scheduled_tasks.purge_broadcast_messages")

    purge_functional_test_alerts(older_than=123)

    mocked_purge.assert_called_with(
        service_id=notify_api.config["FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID"], older_than=123
    )


def test_purge_functional_test_alerts_does_not_run_in_public(mocker):
    mocked_purge = mocker.patch("app.tasks.scheduled_tasks.purge_broadcast_messages")
    mocker.patch("app.tasks.scheduled_tasks.is_public_environment", return_value=True)

    purge_functional_test_alerts()

    mocked_purge.assert_not_called()


def test_purge_functional_test_alerts_does_not_run_without_service_id(notify_api, mocker):
    mocked_purge = mocker.patch("app.tasks.scheduled_tasks.purge_broadcast_messages")
    mocker.patch("app.tasks.scheduled_tasks.is_public_environment", return_value=True)

    with set_config(notify_api, "FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID", None):
        purge_functional_test_alerts()

    mocked_purge.assert_not_called()


@pytest.mark.parametrize(
    "finished_govuk_acknowledged",
    (True, False),
)
def test_queue_after_alert_activities_does_govuk_refresh(notify_api, mocker, finished_govuk_acknowledged):
    task_mock = mocker.patch("app.tasks.scheduled_tasks.publish_govuk_build", return_value=(Mock(), Mock()))

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


def _create_api_key_created_at(service, created_at, key_name=None):
    api_key = create_api_key(service, key_name=key_name or f"key created {created_at}")
    api_key.created_at = created_at
    db.session.commit()
    return api_key


@freeze_time("2026-11-26 09:00:00")
def test_check_api_key_expiry_warns_about_each_key_once(notify_api, sample_service, mocker):
    mock_send = mocker.patch("app.tasks.scheduled_tasks.slack_client.send_message_to_slack")
    overdue = _create_api_key_created_at(sample_service, datetime(2025, 9, 1, 9, 0))
    expiring = _create_api_key_created_at(sample_service, datetime(2025, 12, 10, 14, 30))
    not_yet = _create_api_key_created_at(sample_service, datetime(2026, 6, 1, 9, 0))

    check_api_key_expiry()

    messages = [c.args[0] for c in mock_send.call_args_list]
    assert [m.subject for m in messages] == ["API key is past its expiry date", "API key expires in 14 days"]
    assert [m.message_type for m in messages] == ["error", "info"]
    assert {m.webhook_url for m in messages} == {"https://hooks.slack.com/api-key-expiry"}
    assert overdue.expiry_warning_sent_at == datetime(2026, 11, 26, 9, 0)
    assert expiring.expiry_warning_sent_at == datetime(2026, 11, 26, 9, 0)
    assert not_yet.expiry_warning_sent_at is None

    mock_send.reset_mock()
    check_api_key_expiry()
    mock_send.assert_not_called()


@freeze_time("2026-11-26 09:00:00")
def test_check_api_key_expiry_slack_message_content(notify_api, notify_db_session, mocker):
    mock_send = mocker.patch("app.tasks.scheduled_tasks.slack_client.send_message_to_slack")
    service = create_service(service_name="Floods <North> & East")
    _create_api_key_created_at(service, datetime(2025, 12, 24, 16, 45), key_name="Live key")

    admin_url = "https://admin.emergency-alerts.service.gov.uk"
    with set_config_values(notify_api, {"ENVIRONMENT": "production", "ADMIN_EXTERNAL_URL": admin_url}):
        check_api_key_expiry()

    message = mock_send.call_args.args[0]
    assert message.subject == "API key expires in 28 days"
    assert message.markdown_sections == [
        "*Environment:* production",
        f"*Service:* Floods &lt;North&gt; &amp; East (`{service.id}`)",
        "*Key name:* Live key",
        "*Key type:* normal",
        "*Created:* 24 December 2025",
        "*Expires:* 24 December 2026",
        "Work with the client to replace this key, then revoke it on 24 December 2026 when it reaches 12 months old.",
        f"<{admin_url}/services/{service.id}/api/keys|View API keys for this service>",
    ]


@freeze_time("2026-11-26 09:00:00")
@pytest.mark.parametrize(
    "created_at, expected_subject, expected_type",
    [
        (datetime(2025, 11, 27, 9, 0), "API key expires in 1 day", "info"),
        (datetime(2025, 11, 26, 9, 0), "API key expires today", "error"),
    ],
)
def test_check_api_key_expiry_subject_near_expiry(
    notify_api, sample_service, mocker, created_at, expected_subject, expected_type
):
    mock_send = mocker.patch("app.tasks.scheduled_tasks.slack_client.send_message_to_slack")
    _create_api_key_created_at(sample_service, created_at)

    check_api_key_expiry()

    message = mock_send.call_args.args[0]
    assert message.subject == expected_subject
    assert message.message_type == expected_type


@pytest.mark.parametrize("webhook_url", [None, "", "dummy"])
def test_check_api_key_expiry_does_nothing_without_a_valid_webhook(notify_api, sample_service, mocker, webhook_url):
    mock_send = mocker.patch("app.tasks.scheduled_tasks.slack_client.send_message_to_slack")
    api_key = _create_api_key_created_at(sample_service, datetime(2020, 1, 1, 9, 0))

    with set_config(notify_api, "API_KEY_EXPIRY_SLACK_WEBHOOK_URL", webhook_url):
        check_api_key_expiry()

    mock_send.assert_not_called()
    assert api_key.expiry_warning_sent_at is None


def test_check_api_key_expiry_does_not_record_warning_if_slack_fails(notify_api, sample_service, mocker):
    mocker.patch(
        "app.tasks.scheduled_tasks.slack_client.send_message_to_slack",
        side_effect=SlackError(Mock(status_code=500)),
    )
    api_key = _create_api_key_created_at(sample_service, datetime(2020, 1, 1, 9, 0))

    with pytest.raises(SlackError):
        check_api_key_expiry()

    assert api_key.expiry_warning_sent_at is None
