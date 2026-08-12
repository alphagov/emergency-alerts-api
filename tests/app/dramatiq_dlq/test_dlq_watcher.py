import base64
import json

import pytest

from app.dao.broadcast_message_dao import add_broadcast_provider_message_status
from app.dramatiq_dlq.dlq_watcher import DlqWatcher
from app.models import (
    BROADCAST_PROVIDER_STATUS_ERR,
    BROADCAST_PROVIDER_STATUS_ERR_RETRY_EXHAUSTED,
    BROADCAST_PROVIDER_STATUS_SENDING,
    BroadcastStatusType,
)
from tests.app.db import (
    create_broadcast_event,
    create_broadcast_message,
    create_broadcast_provider_message,
)
from tests.conftest import set_config_values


def test_gets_messages_from_dlq(notify_api, mocker):
    fake_response = {"Messages": [{"MessageId": "id"}]}
    mock_receive_message = mocker.Mock(return_value=fake_response)

    with set_config_values(notify_api, {"DLQ_URL": "mocked", "FAILED_QUEUE_URL": "mocked-failed"}):
        dlq_watcher = DlqWatcher()
        dlq_watcher.sqs_client.receive_message = mock_receive_message

    response = dlq_watcher.get_dlq_messages()
    assert response == fake_response["Messages"]
    assert mock_receive_message.call_args.kwargs["QueueUrl"] == "mocked"
    assert mock_receive_message.call_args.kwargs["WaitTimeSeconds"] == 20


@pytest.mark.parametrize(
    "message_body",
    [
        "not-json",
        {"not-a-dramatiq-message": True},
        {
            "queue_name": "preview-dramatiq-govuk-alerts",
            "actor_name": "publish-govuk-alerts",
            "args": [],
            "kwargs": {"broadcast_event_id": "abcd"},
        },
    ],
)
def test_random_message_forwarded_to_failure_queue(message_body, notify_api, mocker):
    fake_message = {
        "MessageId": "id",
        "ReceiptHandle": "receipt",
        # Turn the JSON body into a base64 *str*
        "Body": base64.b64encode(json.dumps(message_body).encode()).decode(),
    }
    mock_send_message = mocker.Mock()
    mock_delete_message = mocker.Mock()

    with set_config_values(notify_api, {"DLQ_URL": "mocked", "FAILED_QUEUE_URL": "mocked-failed"}):
        dlq_watcher = DlqWatcher()
        dlq_watcher.sqs_client.send_message = mock_send_message
        dlq_watcher.sqs_client.delete_message = mock_delete_message

    dlq_watcher._process_sqs_message(fake_message)

    assert mock_send_message.call_args.kwargs["QueueUrl"] == "mocked-failed"
    # MessageBody will be a string, so parse it to match the dict
    assert json.loads(mock_send_message.call_args.kwargs["MessageBody"]) == fake_message

    assert mock_delete_message.call_args.kwargs["QueueUrl"] == "mocked"
    assert mock_delete_message.call_args.kwargs["ReceiptHandle"] == fake_message["ReceiptHandle"]


def test_failed_broadcast_gets_retry_exhausted_status(notify_api, mocker, sample_broadcast_service):
    bm = create_broadcast_message(
        service=sample_broadcast_service, content="test", status=BroadcastStatusType.BROADCASTING
    )
    sending_event = create_broadcast_event(broadcast_message=bm)
    # Implicitly creates sending status:
    bpm = create_broadcast_provider_message(broadcast_event=sending_event, provider="test")
    add_broadcast_provider_message_status(bpm, status=BROADCAST_PROVIDER_STATUS_ERR)

    fake_message = {
        "MessageId": "id",
        "ReceiptHandle": "receipt",
        # Turn the JSON body into a base64 *str*
        "Body": base64.b64encode(
            json.dumps(
                {
                    "queue_name": "high-priority-tasks",
                    "actor_name": "send-broadcast-provider-message",
                    "args": [],
                    "kwargs": {"broadcast_event_id": str(sending_event.id), "provider": "test"},
                    "options": {},
                }
            ).encode()
        ).decode(),
    }
    mock_send_message = mocker.Mock()
    mock_delete_message = mocker.Mock()

    with set_config_values(notify_api, {"DLQ_URL": "mocked", "FAILED_QUEUE_URL": "mocked-failed"}):
        dlq_watcher = DlqWatcher()
        dlq_watcher.sqs_client.send_message = mock_send_message
        dlq_watcher.sqs_client.delete_message = mock_delete_message

    dlq_watcher._process_sqs_message(fake_message)

    assert mock_send_message.call_args.kwargs["QueueUrl"] == "mocked-failed"
    # MessageBody will be a string, so parse it to match the dict
    assert json.loads(mock_send_message.call_args.kwargs["MessageBody"]) == fake_message

    assert mock_delete_message.call_args.kwargs["QueueUrl"] == "mocked"
    assert mock_delete_message.call_args.kwargs["ReceiptHandle"] == fake_message["ReceiptHandle"]

    bpm = sending_event.get_provider_message("test")

    assert len(bpm.statuses) == 3
    assert bpm.statuses[0].status == BROADCAST_PROVIDER_STATUS_SENDING
    assert bpm.statuses[1].status == BROADCAST_PROVIDER_STATUS_ERR
    assert bpm.statuses[2].status == BROADCAST_PROVIDER_STATUS_ERR_RETRY_EXHAUSTED
    assert bpm.get_latest_status_entry() == bpm.statuses[2]
