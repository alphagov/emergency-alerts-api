import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import botocore.exceptions

from app.dao.broadcast_service_dao import set_service_broadcast_providers
from app.models import BROADCAST_TYPE, BroadcastStatusType
from app.tasks.log_ingest_tasks import (
    _build_payload,
    _invoke_log_upload_lambda,
    request_log_ingest_task,
)
from tests.app.db import (
    create_broadcast_event,
    create_broadcast_message,
    create_broadcast_provider_message,
    create_template,
)
from tests.conftest import set_config


def test_request_log_ingest_task_returns_early_if_event_not_found(mocker, notify_api):
    # When the broadcast event does not exist, the task should exit immediately
    # without invoking the Lambda or scheduling a retry.
    mocker.patch("app.tasks.log_ingest_tasks.BroadcastEvent.query").get.return_value = None
    mock_invoke = mocker.patch("app.tasks.log_ingest_tasks._invoke_log_upload_lambda")
    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    request_log_ingest_task(broadcast_event_id=str(uuid.uuid4()))

    mock_invoke.assert_not_called()
    mock_send_with_options.assert_not_called()


def test_request_log_ingest_task_invokes_lambda_and_completes_when_all_providers_sent(
    mocker, notify_api, sample_broadcast_service
):
    # When all enabled providers have provider messages, the Lambda should be invoked
    # once with the correct MNO IDs and no retry should be scheduled.
    set_service_broadcast_providers(sample_broadcast_service, ["ee", "vodafone"])
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    create_broadcast_provider_message(event, "ee")
    create_broadcast_provider_message(event, "vodafone")

    mock_invoke = mocker.patch("app.tasks.log_ingest_tasks._invoke_log_upload_lambda", return_value=True)
    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}):
        with set_config(notify_api, "LOG_UPLOAD_LAMBDA_ARN", "arn:aws:lambda:eu-west-2:123:function:test"):
            request_log_ingest_task(broadcast_event_id=str(event.id))

    mock_invoke.assert_called_once()
    payload = mock_invoke.call_args[0][1]
    mno_ids = {m["mno_id"] for m in payload["mnos"]}
    assert mno_ids == {"EE", "VODAFONE"}
    mock_send_with_options.assert_not_called()


def test_request_log_ingest_task_skips_already_sent_provider_ids(mocker, notify_api, sample_broadcast_service):
    # When all provider messages are already in the sent_provider_ids list,
    # the Lambda should not be invoked again and no retry should be scheduled.
    set_service_broadcast_providers(sample_broadcast_service, ["ee"])
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    pm_ee = create_broadcast_provider_message(event, "ee")

    mock_invoke = mocker.patch("app.tasks.log_ingest_tasks._invoke_log_upload_lambda")
    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    with set_config(notify_api, "ENABLED_CBCS", {"ee"}):
        with set_config(notify_api, "LOG_UPLOAD_LAMBDA_ARN", "arn:aws:lambda:eu-west-2:123:function:test"):
            request_log_ingest_task(
                broadcast_event_id=str(event.id),
                sent_provider_ids=[str(pm_ee.id)],
            )

    mock_invoke.assert_not_called()
    mock_send_with_options.assert_not_called()


def test_request_log_ingest_task_retries_when_providers_not_yet_ready(mocker, notify_api, sample_broadcast_service):
    # When only some providers have messages (vodafone is missing here), the task should
    # invoke the Lambda for the ready provider and schedule a retry carrying the
    # incremented attempt count and the IDs already sent.
    set_service_broadcast_providers(sample_broadcast_service, ["ee", "vodafone"])
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    pm_ee = create_broadcast_provider_message(event, "ee")
    # vodafone provider message does not exist yet

    mocker.patch("app.tasks.log_ingest_tasks._invoke_log_upload_lambda", return_value=True)
    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}):
        with set_config(notify_api, "LOG_UPLOAD_LAMBDA_ARN", "arn:aws:lambda:eu-west-2:123:function:test"):
            request_log_ingest_task(broadcast_event_id=str(event.id), attempt=0)

    mock_send_with_options.assert_called_once()
    kwargs = mock_send_with_options.call_args[1]["kwargs"]
    assert kwargs["attempt"] == 1
    assert kwargs["broadcast_event_id"] == str(event.id)
    assert str(pm_ee.id) in kwargs["sent_provider_ids"]


def test_request_log_ingest_task_logs_error_at_max_retries_with_nothing_sent(
    mocker, notify_api, sample_broadcast_service
):
    # At max retries with no provider messages sent at all, the task should stop
    # and not schedule another retry.
    set_service_broadcast_providers(sample_broadcast_service, ["ee"])
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    # No provider messages at all

    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    with set_config(notify_api, "ENABLED_CBCS", {"ee"}):
        with set_config(notify_api, "LOG_UPLOAD_LAMBDA_ARN", "arn:aws:lambda:eu-west-2:123:function:test"):
            request_log_ingest_task(broadcast_event_id=str(event.id), attempt=5)

    mock_send_with_options.assert_not_called()


def test_request_log_ingest_task_logs_warning_at_max_retries_with_partial_sent(
    mocker, notify_api, sample_broadcast_service
):
    # At max retries with only some providers sent, the task should stop
    # and not schedule another retry.
    set_service_broadcast_providers(sample_broadcast_service, ["ee", "vodafone"])
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    pm_ee = create_broadcast_provider_message(event, "ee")

    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    with set_config(notify_api, "ENABLED_CBCS", {"ee", "vodafone"}):
        with set_config(notify_api, "LOG_UPLOAD_LAMBDA_ARN", "arn:aws:lambda:eu-west-2:123:function:test"):
            request_log_ingest_task(
                broadcast_event_id=str(event.id),
                attempt=5,
                sent_provider_ids=[str(pm_ee.id)],
            )

    mock_send_with_options.assert_not_called()


def test_request_log_ingest_task_returns_early_when_lambda_arn_not_configured(
    mocker, notify_api, sample_broadcast_service
):
    # When LOG_UPLOAD_LAMBDA_ARN is empty, the task should return early without
    # invoking the Lambda or scheduling a retry.
    set_service_broadcast_providers(sample_broadcast_service, ["ee"])
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)
    create_broadcast_provider_message(event, "ee")

    mock_invoke = mocker.patch("app.tasks.log_ingest_tasks._invoke_log_upload_lambda")
    mock_send_with_options = mocker.patch("app.tasks.log_ingest_tasks.request_log_ingest_task.send_with_options")

    with set_config(notify_api, "ENABLED_CBCS", {"ee"}):
        with set_config(notify_api, "LOG_UPLOAD_LAMBDA_ARN", ""):
            request_log_ingest_task(broadcast_event_id=str(event.id))

    mock_invoke.assert_not_called()
    mock_send_with_options.assert_not_called()


def test_build_payload_returns_correct_structure(notify_api, sample_broadcast_service):
    # Asserts that _build_payload produces a dict with the correct alert reference,
    # environment, broadcast window timestamps, and MNO list structure.
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
        payload = _build_payload(event, [pm_ee])

    assert payload["alert_reference"] == str(event.id)
    assert payload["environment"] == "test"
    assert payload["broadcast_start"] == starts_at.replace(tzinfo=None).isoformat()
    assert payload["broadcast_end"] == finishes_at.replace(tzinfo=None).isoformat()
    assert payload["mnos"] == [{"mno_id": "EE", "provider_message_id": str(pm_ee.id)}]


def test_build_payload_handles_none_transmitted_starts_at(notify_api, sample_broadcast_service):
    # When transmitted_starts_at is None, _build_payload should return broadcast_start
    # as None rather than raising an error.
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message, transmitted_starts_at=None)
    pm_ee = create_broadcast_provider_message(event, "ee")

    payload = _build_payload(event, [pm_ee])

    assert payload["broadcast_start"] is None


def test_invoke_log_upload_lambda_returns_true_on_202(mocker, notify_api):
    # When Lambda invocation returns a 202 (async accepted), the function should
    # return True and have called invoke with the correct ARN, invocation type, and JSON payload.
    mock_client = MagicMock()
    mock_client.invoke.return_value = {"StatusCode": 202}
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    result = _invoke_log_upload_lambda("arn:aws:lambda:eu-west-2:123:function:test", {"key": "value"})

    assert result is True
    mock_client.invoke.assert_called_once_with(
        FunctionName="arn:aws:lambda:eu-west-2:123:function:test",
        InvocationType="Event",
        Payload=b'{"key": "value"}',
    )


def test_invoke_log_upload_lambda_returns_false_on_non_202(mocker, notify_api):
    # When Lambda invocation returns any non-202 status code, the function should return False.
    mock_client = MagicMock()
    mock_client.invoke.return_value = {"StatusCode": 500}
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    result = _invoke_log_upload_lambda("arn:aws:lambda:eu-west-2:123:function:test", {})

    assert result is False


def test_invoke_log_upload_lambda_returns_false_on_client_error(mocker, notify_api):
    # When boto3 raises a ClientError (e.g. function not found), the function
    # should catch it and return False rather than propagating the exception.
    mock_client = MagicMock()
    mock_client.invoke.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Function not found"}},
        "Invoke",
    )
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    result = _invoke_log_upload_lambda("arn:aws:lambda:eu-west-2:123:function:test", {})

    assert result is False


def test_invoke_log_upload_lambda_returns_false_on_generic_exception(mocker, notify_api):
    # When any unexpected exception is raised during invocation, the function
    # should catch it and return False rather than propagating the exception.
    mock_client = MagicMock()
    mock_client.invoke.side_effect = Exception("network error")
    mocker.patch("app.tasks.log_ingest_tasks.boto3.client", return_value=mock_client)

    result = _invoke_log_upload_lambda("arn:aws:lambda:eu-west-2:123:function:test", {})

    assert result is False
