"""
This module handles the post-broadcast log ingest flow.

After a broadcast event is sent to the MNOs, each MNO generates a CBC log for
that broadcast. This task invokes the mno-portal-{environment}-log-upload-handler
lambda, which sends an email to each MNO requesting that they upload their CBC log
for the broadcast.

Because the broadcast_provider_message records (which carry the unique IDs that
identify the broadcast to each MNO) may not exist immediately after the alert is
accepted, the task retries up to _MAX_ATTEMPTS times before giving up.
"""

import json

import boto3
import botocore.exceptions
from emergency_alerts_utils.tasks import QueueNames, TaskNames
from flask import current_app

from app import dramatiq
from app.dao.broadcast_message_dao import (
    dao_get_broadcast_provider_messages_for_event,
)
from app.models import BroadcastEvent

_MAX_ATTEMPTS = 5
_RETRY_DELAY_MS = 30_000


def _mno_log_upload_handler_arn():
    # Return the ARN for the MNO portal log upload handler lambda.

    account_number = current_app.config.get("MNO_PORTAL_ACCOUNT_NUMBER")
    environment = current_app.config.get("ENVIRONMENT_PREFIX") or current_app.config.get("ENVIRONMENT")
    function_name = f"mno-portal-{environment}-log-upload-handler"
    if account_number:
        return f"{account_number}:function:{function_name}"
    return None


@dramatiq.actor(actor_name=TaskNames.REQUEST_LOG_INGEST, queue_name=QueueNames.HIGH_PRIORITY)
def send_broadcast_log_upload_request_emails_task(broadcast_event_id, attempt=0, sent_provider_ids=None):
    try:
        current_app.logger.info(
            "Starting send_broadcast_log_upload_request_emails_task",
            extra={"broadcast_event_id": broadcast_event_id},
        )

        broadcast_event = BroadcastEvent.query.get(broadcast_event_id)
        if not broadcast_event:
            current_app.logger.error(
                f"Broadcast event {broadcast_event_id} not found", extra={"broadcast_event_id": broadcast_event_id}
            )
            return

        sent_ids = set(sent_provider_ids or [])
        available_providers = broadcast_event.service.get_available_broadcast_providers()
        provider_messages = dao_get_broadcast_provider_messages_for_event(broadcast_event_id)
        at_max_retries = attempt >= _MAX_ATTEMPTS

        # Provider messages that haven't been included in a log upload request yet
        new_messages = [pm for pm in provider_messages if str(pm.id) not in sent_ids]

        if new_messages:
            lambda_arn = _mno_log_upload_handler_arn()
            if not lambda_arn:
                current_app.logger.error(
                    "_mno_log_upload_handler_arn not configured — cannot invoke MNO log upload lambda"
                )
                return

            log_upload_request = _build_mno_log_upload_request(broadcast_event, new_messages)
            current_app.logger.info(
                "Built MNO log upload request",
                extra={
                    "alert_reference": str(broadcast_event.id),
                    "log_upload_request": json.dumps(log_upload_request),
                },
            )

            if _trigger_mno_log_upload_request(lambda_arn, log_upload_request):
                sent_ids |= {str(pm.id) for pm in new_messages}
                current_app.logger.info(
                    "Successfully triggered MNO log upload request emails",
                    extra={"broadcast_event_id": broadcast_event_id},
                )
            else:
                current_app.logger.error(
                    "Failed to trigger MNO log upload request emails",
                    extra={"broadcast_event_id": broadcast_event_id},
                )

        providers_sent = {pm.provider for pm in provider_messages if str(pm.id) in sent_ids}
        all_providers_done = providers_sent >= set(available_providers)

        if all_providers_done:
            return

        if at_max_retries:
            if not sent_ids:
                current_app.logger.error(
                    f"No log upload request emails sent for broadcast_event {broadcast_event_id} after {attempt} "
                    f"attempts. Provider messages may not have been created.",
                    extra={"broadcast_event_id": broadcast_event_id},
                )
            else:
                current_app.logger.warning(
                    f"Max retries exceeded: only sent for {len(providers_sent)}/{len(available_providers)} "
                    f"providers for broadcast_event {broadcast_event_id}.",
                    extra={"broadcast_event_id": broadcast_event_id},
                )
            return

        missing = set(available_providers) - providers_sent
        current_app.logger.warning(
            f"Providers {missing} not yet sent, retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
            extra={"broadcast_event_id": broadcast_event_id},
        )
        send_broadcast_log_upload_request_emails_task.send_with_options(
            kwargs={
                "broadcast_event_id": broadcast_event_id,
                "attempt": attempt + 1,
                "sent_provider_ids": list(sent_ids),
            },
            delay=_RETRY_DELAY_MS,
        )

    except Exception as e:
        current_app.logger.exception(
            f"Error in send_broadcast_log_upload_request_emails_task for broadcast_event {broadcast_event_id}",
            extra={
                "exception_type": type(e).__name__,
                "python_module": __name__,
                "exception": str(e),
                "broadcast_event_id": broadcast_event_id,
            },
        )
        raise


def _build_mno_log_upload_request(broadcast_event, provider_messages):
    """Build the request body sent to the MNO portal log upload handler lambda.

    The lambda uses this to email each MNO with the broadcast identifiers they
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
                "mno_id": pm.provider.upper(),
                "provider_message_id": str(pm.id),
            }
            for pm in provider_messages
        ],
    }


def _trigger_mno_log_upload_request(lambda_arn, log_upload_request):
    """Invoke the MNO portal log upload handler lambda asynchronously.

    The lambda sends an email to each MNO listed in log_upload_request, asking
    them to upload their CBC log for the broadcast identified by alert_reference.
    """
    lambda_client = boto3.client("lambda", region_name="eu-west-2")
    payload_bytes = bytes(json.dumps(log_upload_request), encoding="utf8")

    try:
        current_app.logger.info(
            f"Invoking MNO log upload handler {lambda_arn}",
            extra={
                "log_upload_request": str(log_upload_request),
                "lambda_invocation_type": "Event",
            },
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
