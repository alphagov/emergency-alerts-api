import base64
import json
import logging

import boto3
from dramatiq.message import Message
from emergency_alerts_utils.tasks import TaskNames
from flask import current_app

from app.dao.broadcast_message_dao import (
    add_broadcast_provider_message_status,
    dao_get_broadcast_event_by_id,
)
from app.models import BROADCAST_PROVIDER_STATUS_ERR_RETRY_EXHAUSTED


class DlqWatcher:
    """
    A class that looks at the SQS' DLQ directly and watches for failed tasks that end up on it.
    Failed Dramatiq tasks that end up here will have been retried many times already and SQS has given up on them.
    Broadcasts tasks will have their BroadcastProviderMessageStatus updated accordingly to a 'permanently failed'
    status. Then all given messages/tasks will be put onto another queue for manual intervention.

    Assumes running under a Flask app context.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.sqs_client = boto3.client("sqs")
        self.dlq_url = current_app.config["DLQ_URL"]
        self.failed_queue_url = current_app.config["FAILED_QUEUE_URL"]
        self.stop = False

        assert self.dlq_url is not None, "DLQ_URL must be configured"
        assert self.failed_queue_url is not None, "FAILED_QUEUE_URL must be configured"

    def get_dlq_messages(self):
        # See https://docs.aws.amazon.com/boto3/latest/reference/services/sqs/client/receive_message.html
        response = self.sqs_client.receive_message(
            QueueUrl=self.dlq_url,
            WaitTimeSeconds=20,  # Long polling
            MessageAttributeNames=["All"],
            AttributeNames=["All"],
        )

        messages = response.get("Messages", [])
        self.logger.info("Got SQS messages: %s", messages)
        return messages

    def _process_sqs_message(self, sqs_message: dict):
        try:
            self.logger.info("Processing DLQ message %s", sqs_message["MessageId"])

            message_body_base64 = sqs_message["Body"]
            # Dramatiq encodes messages as base64-ed JSON. Decode it.
            message_body_json = base64.b64decode(message_body_base64)
            self.logger.info("Base64 decoded message body: %s", message_body_json)

            message_body = json.loads(message_body_json)
            message = Message(**message_body)

            if message.actor_name == TaskNames.SEND_BROADCAST_PROVIDER_MESSAGE:
                # This is a failed broadcast, update the status accordingly.
                self.logger.info("Was broadcast task, setting failed status")
                self._add_final_failed_status(message.kwargs["broadcast_event_id"], message.kwargs["provider"])
        finally:
            # Regardless of 'processability', forward the message to the failed SQS queue
            self._send_to_failed_queue(sqs_message)

            self.sqs_client.delete_message(QueueUrl=self.dlq_url, ReceiptHandle=sqs_message["ReceiptHandle"])
            pass

    def _send_to_failed_queue(self, sqs_message):
        result = self.sqs_client.send_message(QueueUrl=self.failed_queue_url, MessageBody=json.dumps(sqs_message))
        self.logger.info("Sent message to failed queue: %s", result)

    def _add_final_failed_status(self, broadcast_event_id: str, provider: str):
        broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)
        broadcast_provider_message = broadcast_event.get_provider_message(provider)

        add_broadcast_provider_message_status(
            broadcast_provider_message, status=BROADCAST_PROVIDER_STATUS_ERR_RETRY_EXHAUSTED
        )
        self.logger.info(
            "Added BROADCAST_PROVIDER_STATUS_ERR_RETRY_EXHAUSTED status for BroadcastProviderMessage ID: %s",
            broadcast_provider_message.id,
        )

    def run(self):
        self.logger.info("Running DlqWatcher")

        while not self.stop:
            messages = self.get_dlq_messages()
            for message in messages:
                self._process_sqs_message(message)

        self.logger.info("DlqWatcher stopped")
