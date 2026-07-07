"""
This module triggers a log upload request email to each MNO after their broadcast
has been successfully sent.

After send_broadcast_provider_message confirms a broadcast has been accepted by an MNO,
it enqueues send_mno_log_upload_request_email_task for that MNO. This task
invokes the mno-portal-{environment}-log-upload-handler lambda, which emails the MNO
requesting they upload their CBC log for the broadcast.
"""

import json

import boto3
import botocore.exceptions
from emergency_alerts_utils.tasks import QueueNames, TaskNames
from flask import current_app

from app import dramatiq
from app.models import BroadcastEvent, BroadcastProviderMessage


def _mno_log_upload_handler_arn():
    account_number = current_app.config.get("MNO_PORTAL_ACCOUNT_NUMBER")
    environment = current_app.config.get("ENVIRONMENT")
    if not account_number:
        return None
    return f"{account_number}:function:mno-portal-{environment}-log-upload-handler"


@dramatiq.actor(actor_name=TaskNames.REQUEST_LOG_INGEST, queue_name=QueueNames.HIGH_PRIORITY)
def send_mno_log_upload_request_email_task(broadcast_event_id, provider_message_id):
    broadcast_event = BroadcastEvent.query.get(broadcast_event_id)
    if not broadcast_event:
        current_app.logger.error(
            f"Broadcast event {broadcast_event_id} not found",
            extra={"broadcast_event_id": broadcast_event_id},
        )
        return

    provider_message = BroadcastProviderMessage.query.get(provider_message_id)
    if not provider_message:
        current_app.logger.error(
            f"BroadcastProviderMessage {provider_message_id} not found",
            extra={"provider_message_id": provider_message_id, "broadcast_event_id": broadcast_event_id},
        )
        return

    log_upload_request = _build_mno_log_upload_request(broadcast_event, provider_message)

    if _trigger_mno_log_upload_request(log_upload_request):
        current_app.logger.info(
            "Successfully triggered MNO log upload request email",
            extra={"broadcast_event_id": broadcast_event_id, "provider_message_id": provider_message_id},
        )
    else:
        current_app.logger.error(
            "Failed to trigger MNO log upload request email",
            extra={"broadcast_event_id": broadcast_event_id, "provider_message_id": provider_message_id},
        )


def _build_mno_log_upload_request(broadcast_event, provider_message):
    """Build the request body sent to the MNO portal log upload handler lambda.

    The lambda uses this to email the MNO with the broadcast identifiers they
    need to locate and upload their CBC log for the broadcast.
    """
    return {
        "alert_reference": str(broadcast_event.id),
        "environment": current_app.config.get("ENVIRONMENT"),
        "broadcast_start": (
            broadcast_event.transmitted_starts_at.isoformat() if broadcast_event.transmitted_starts_at else None
        ),
        "broadcast_end": (
            broadcast_event.transmitted_finishes_at.isoformat() if broadcast_event.transmitted_finishes_at else None
        ),
        "mnos": [
            {
                "mno_id": provider_message.provider.upper(),
                "provider_message_id": str(provider_message.id),
            }
        ],
    }


def _trigger_mno_log_upload_request(log_upload_request):
    """Invoke the MNO portal log upload handler lambda asynchronously.

    The lambda sends an email to the MNO requesting they upload their CBC log
    for the broadcast identified by alert_reference.
    """
    lambda_arn = _mno_log_upload_handler_arn()
    if not lambda_arn:
        current_app.logger.error("MNO_PORTAL_ACCOUNT_NUMBER not configured — cannot invoke MNO log upload handler")
        return False

    lambda_client = boto3.client("lambda", region_name="eu-west-2")
    payload_bytes = bytes(json.dumps(log_upload_request), encoding="utf8")

    try:
        current_app.logger.info(
            f"Invoking MNO log upload handler {lambda_arn}",
            extra={"log_upload_request": str(log_upload_request), "lambda_invocation_type": "Event"},
        )

        response = lambda_client.invoke(
            FunctionName=lambda_arn,
            InvocationType="Event",
            Payload=payload_bytes,
        )

        if response["StatusCode"] == 202:
            current_app.logger.info(
                f"Successfully invoked MNO log upload handler {lambda_arn}",
                extra={"status_code": response["StatusCode"]},
            )
            return True
        else:
            current_app.logger.error(
                f"Error invoking MNO log upload handler {lambda_arn}",
                extra={"status_code": response["StatusCode"]},
            )
            return False

    except botocore.exceptions.ClientError as e:
        current_app.logger.error(
            f"Boto3 ClientError invoking MNO log upload handler {lambda_arn}",
            extra={"python_module": __name__, "error": str(e)},
        )
        return False

    except Exception as e:
        current_app.logger.error(
            f"Unexpected error invoking MNO log upload handler {lambda_arn}",
            extra={"python_module": __name__, "error": str(e)},
        )
        return False
