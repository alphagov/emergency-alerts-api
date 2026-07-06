import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import botocore.exceptions

from app.models import BROADCAST_TYPE, BroadcastStatusType
from app.tasks.log_ingest_tasks import (
    _build_mno_log_upload_request,
    _trigger_mno_log_upload_request,
    send_mno_log_upload_request_email_task,
)
from tests.app.db import (
    create_broadcast_event,
    create_broadcast_message,
    create_broadcast_provider_message,
    create_template,
)
from tests.conftest import set_config


def test_send_mno_log_upload_request_email_task_returns_early_if_event_not_found(mocker, notify_api):
    mocker.patch("app.tasks.log_ingest_tasks.BroadcastEvent.query").get.return_value = None
    mock_trigger = mocker.patch("app.tasks.log_ingest_tasks._trigger_mno_log_upload_request")

    send_mno_log_upload_request_email_task(broadcast_event_id=str(uuid.uuid4()), provider_message_id=str(uuid.uuid4()))

    mock_trigger.assert_not_called()


def test_send_mno_log_upload_request_email_task_returns_early_if_provider_message_not_found(
    mocker, notify_api, sample_broadcast_service
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)

    mock_trigger = mocker.patch("app.tasks.log_ingest_tasks._trigger_mno_log_upload_request")

    send_mno_log_upload_request_email_task(broadcast_event_id=str(event.id), provider_message_id=str(uuid.uuid4()))

    mock_trigger.assert_not_called()


def test_send_mno_log_upload_request_email_task_triggers_lambda_for_provider_message(
    mocker, notify_api, sample_broadcast_service
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    pm_ee = create_broadcast_provider_message(event, "ee")

    mock_trigger = mocker.patch("app.tasks.log_ingest_tasks._trigger_mno_log_upload_request", return_value=True)

    send_mno_log_upload_request_email_task(broadcast_event_id=str(event.id), provider_message_id=str(pm_ee.id))

    mock_trigger.assert_called_once()
    log_upload_request = mock_trigger.call_args[0][0]
    assert log_upload_request["mnos"] == [{"mno_id": "EE", "provider_message_id": str(pm_ee.id)}]


def test_build_mno_log_upload_request_returns_correct_structure(notify_api, sample_broadcast_service):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    starts_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    finishes_at = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    event = create_broadcast_event(
        broadcast_message,
        transmitted_starts_at=starts_at,
        transmitted_finishes_at=finishes_at,
    )
    pm_ee = create_broadcast_provider_message(event, "ee")

    with set_config(notify_api, "ENVIRONMENT", "test"):
        log_upload_request = _build_mno_log_upload_request(event, pm_ee)

    assert log_upload_request["alert_reference"] == str(event.id)
    assert log_upload_request["environment"] == "test"
    assert log_upload_request["broadcast_start"] == starts_at.replace(tzinfo=None).isoformat()
    assert log_upload_request["broadcast_end"] == finishes_at.replace(tzinfo=None).isoformat()
    assert log_upload_request["mnos"] == [{"mno_id": "EE", "provider_message_id": str(pm_ee.id)}]


def test_build_mno_log_upload_request_handles_none_transmitted_starts_at(notify_api, sample_broadcast_service):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message, transmitted_starts_at=None)
    pm_ee = create_broadcast_provider_message(event, "ee")

    log_upload_request = _build_mno_log_upload_request(event, pm_ee)

    assert log_upload_request["broadcast_start"] is None


def test_trigger_mno_log_upload_request_returns_true_on_202(mocker, notify_api):
    mock_client = MagicMock()
    mock_client.invoke.return_value = {"StatusCode": 202}
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    with set_config(notify_api, "MNO_PORTAL_ACCOUNT_NUMBER", "123456789012"):
        with set_config(notify_api, "ENVIRONMENT", "staging"):
            result = _trigger_mno_log_upload_request({"key": "value"})

    assert result is True
    mock_client.invoke.assert_called_once_with(
        FunctionName="123456789012:function:mno-portal-staging-log-upload-handler",
        InvocationType="Event",
        Payload=b'{"key": "value"}',
    )


def test_trigger_mno_log_upload_request_returns_false_when_account_number_not_configured(mocker, notify_api):
    mock_client = MagicMock()
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    with set_config(notify_api, "MNO_PORTAL_ACCOUNT_NUMBER", None):
        result = _trigger_mno_log_upload_request({"key": "value"})

    assert result is False
    mock_client.invoke.assert_not_called()


def test_trigger_mno_log_upload_request_returns_false_on_non_202(mocker, notify_api):
    mock_client = MagicMock()
    mock_client.invoke.return_value = {"StatusCode": 500}
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    with set_config(notify_api, "MNO_PORTAL_ACCOUNT_NUMBER", "123456789012"):
        with set_config(notify_api, "ENVIRONMENT", "staging"):
            result = _trigger_mno_log_upload_request({})

    assert result is False


def test_trigger_mno_log_upload_request_returns_false_on_client_error(mocker, notify_api):
    mock_client = MagicMock()
    mock_client.invoke.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Function not found"}},
        "Invoke",
    )
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    with set_config(notify_api, "MNO_PORTAL_ACCOUNT_NUMBER", "123456789012"):
        with set_config(notify_api, "ENVIRONMENT", "staging"):
            result = _trigger_mno_log_upload_request({})

    assert result is False


def test_trigger_mno_log_upload_request_returns_false_on_generic_exception(mocker, notify_api):
    mock_client = MagicMock()
    mock_client.invoke.side_effect = Exception("network error")
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    with set_config(notify_api, "MNO_PORTAL_ACCOUNT_NUMBER", "123456789012"):
        with set_config(notify_api, "ENVIRONMENT", "staging"):
            result = _trigger_mno_log_upload_request({})

    assert result is False
