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


@dramatiq.actor(actor_name=TaskNames.REQUEST_LOG_INGEST, queue_name=QueueNames.HIGH_PRIORITY)
def request_log_ingest_task(broadcast_event_id, attempt=0):
    try:
        current_app.logger.info("Starting request_log_ingest_task", extra={"broadcast_event_id": broadcast_event_id})

        broadcast_event = BroadcastEvent.query.get(broadcast_event_id)
        if not broadcast_event:
            current_app.logger.error(
                f"Broadcast event {broadcast_event_id} not found", extra={"broadcast_event_id": broadcast_event_id}
            )
            return

        available_providers = broadcast_event.service.get_available_broadcast_providers()
        provider_messages = dao_get_broadcast_provider_messages_for_event(broadcast_event_id)

        if len(provider_messages) < len(available_providers):
            if attempt < _MAX_ATTEMPTS:
                current_app.logger.warning(
                    f"Only {len(provider_messages)}/{len(available_providers)} provider messages exist yet, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})",
                    extra={"broadcast_event_id": broadcast_event_id},
                )
                request_log_ingest_task.send_with_options(
                    kwargs={"broadcast_event_id": broadcast_event_id, "attempt": attempt + 1},
                    delay=_RETRY_DELAY_MS,
                )
                return
            else:
                current_app.logger.warning(
                    f"Max retries exceeded waiting for provider messages for broadcast_event {broadcast_event_id}. "
                    f"Proceeding with available provider messages.",
                    extra={"broadcast_event_id": broadcast_event_id},
                )
                if not provider_messages:
                    current_app.logger.error(
                        f"No provider messages found for broadcast_event {broadcast_event_id} after max retries. "
                        f"Cannot send log upload invitations.",
                        extra={"broadcast_event_id": broadcast_event_id},
                    )
                    return

        payload = {
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

        current_app.logger.info(
            "Built Lambda payload", extra={"alert_reference": str(broadcast_event.id), "payload": json.dumps(payload)}
        )

        lambda_arn = current_app.config.get("LOG_UPLOAD_LAMBDA_ARN")

        current_app.logger.info(
            "About to invoke Lambda", extra={"lambda_arn": lambda_arn, "has_lambda_arn": lambda_arn is not None}
        )

        if not lambda_arn:
            current_app.logger.error("LOG_UPLOAD_LAMBDA_ARN not configured!")
            return

        success = _invoke_log_upload_lambda(lambda_arn, payload)

        if success:
            current_app.logger.info(
                "Successfully invoked log upload Lambda",
                extra={"broadcast_event_id": broadcast_event_id},
            )
        else:
            current_app.logger.error(
                "Failed to invoke log upload Lambda",
                extra={"broadcast_event_id": broadcast_event_id},
            )

    except Exception as e:
        current_app.logger.exception(
            f"Error in request_log_ingest_task for broadcast_event {broadcast_event_id}",
            extra={
                "exception_type": type(e).__name__,
                "python_module": __name__,
                "exception": str(e),
                "broadcast_event_id": broadcast_event_id,
            },
        )
        raise


def _invoke_log_upload_lambda(lambda_name, payload):
    lambda_client = boto3.client("lambda", region_name="eu-west-2")
    payload_bytes = bytes(json.dumps(payload), encoding="utf8")

    try:
        current_app.logger.info(
            f"Calling log upload lambda {lambda_name}",
            extra={
                "lambda_payload": str(payload),
                "lambda_invocation_type": "Event",
            },
        )

        response = lambda_client.invoke(
            FunctionName=lambda_name,
            InvocationType="Event",
            Payload=payload_bytes,
        )

        if response["StatusCode"] == 202:
            current_app.logger.info(
                f"Successfully invoked log upload lambda {lambda_name}",
                extra={"status_code": response["StatusCode"]},
            )
            return True
        else:
            current_app.logger.error(
                f"Error invoking log upload lambda {lambda_name}",
                extra={"status_code": response["StatusCode"]},
            )
            return False

    except botocore.exceptions.ClientError as e:
        current_app.logger.error(
            f"Boto3 ClientError calling log upload lambda {lambda_name}",
            extra={"python_module": __name__, "error": str(e)},
        )
        return False

    except Exception as e:
        current_app.logger.error(
            f"Unexpected error calling log upload lambda {lambda_name}",
            extra={"python_module": __name__, "error": str(e)},
        )
        return False
