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
def request_log_ingest_task(broadcast_event_id, attempt=0, sent_provider_ids=None):
    try:
        current_app.logger.info("Starting request_log_ingest_task", extra={"broadcast_event_id": broadcast_event_id})

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

        new_messages = [pm for pm in provider_messages if str(pm.id) not in sent_ids]

        if new_messages:
            lambda_arn = current_app.config.get("LOG_UPLOAD_LAMBDA_ARN")
            if not lambda_arn:
                current_app.logger.error("LOG_UPLOAD_LAMBDA_ARN not configured!")
                return

            payload = _build_payload(broadcast_event, new_messages)
            current_app.logger.info(
                "Built Lambda payload",
                extra={"alert_reference": str(broadcast_event.id), "payload": json.dumps(payload)},
            )
            current_app.logger.info("About to invoke Lambda", extra={"lambda_arn": lambda_arn, "has_lambda_arn": True})

            if _invoke_log_upload_lambda(lambda_arn, payload):
                sent_ids |= {str(pm.id) for pm in new_messages}
                current_app.logger.info(
                    "Successfully invoked log upload Lambda",
                    extra={"broadcast_event_id": broadcast_event_id},
                )
            else:
                current_app.logger.error(
                    "Failed to invoke log upload Lambda",
                    extra={"broadcast_event_id": broadcast_event_id},
                )

        providers_sent = {pm.provider for pm in provider_messages if str(pm.id) in sent_ids}
        all_providers_done = providers_sent >= set(available_providers)

        if all_providers_done:
            return

        if at_max_retries:
            if not sent_ids:
                current_app.logger.error(
                    f"No provider messages sent for broadcast_event {broadcast_event_id} after {attempt} attempts. "
                    f"Cannot send log upload invitations.",
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
        request_log_ingest_task.send_with_options(
            kwargs={
                "broadcast_event_id": broadcast_event_id,
                "attempt": attempt + 1,
                "sent_provider_ids": list(sent_ids),
            },
            delay=_RETRY_DELAY_MS,
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


def _build_payload(broadcast_event, provider_messages):
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
