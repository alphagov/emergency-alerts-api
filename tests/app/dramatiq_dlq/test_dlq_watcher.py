import base64
import json

from app.dramatiq_dlq.dlq_watcher import DlqWatcher
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


def test_random_message_forwarded_to_failure_queue(notify_api, mocker):
    fake_message = {
        "MessageId": "id",
        "ReceiptHandle": "receipt",
        # Turn the JSON object into a base64 *str*
        "Body": base64.b64encode(json.dumps({"not-a-dramatiq-message": True}).encode()).decode(),
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
