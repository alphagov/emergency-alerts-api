import json

import boto3
import botocore.exceptions
from flask import current_app

from app import notify_celery
from app.celery.tasks import TaskNames
from app.models import BroadcastEvent


@notify_celery.task(name=TaskNames.REQUEST_LOG_INGEST)
def request_log_ingest_task(broadcast_event_id):
    """
    Invokes the operator portal log upload Lambda to send invite emails to MNOs
    after a broadcast has been sent.
    """
    try:
        # Get broadcast event details
        broadcast_event = BroadcastEvent.query.get(broadcast_event_id)
        if not broadcast_event:
            current_app.logger.error(
                f"Broadcast event {broadcast_event_id} not found", extra={"broadcast_event_id": broadcast_event_id}
            )
            return False

        broadcast = broadcast_event.broadcast

        # Build payload for Lambda
        payload = {
            "alert_reference": broadcast.reference,
            "environment": current_app.config.get("ENVIRONMENT"),
            "broadcast_start": (
                broadcast_event.transmitted_starts_at.isoformat() if broadcast_event.transmitted_starts_at else None
            ),
            "broadcast_end": (
                broadcast_event.transmitted_finishes_at.isoformat() if broadcast_event.transmitted_finishes_at else None
            ),
            "mnos": _get_mno_details(broadcast),
        }

        # Invoke the Lambda
        lambda_name = current_app.config.get("LOG_UPLOAD_LAMBDA_NAME")
        success = _invoke_log_upload_lambda(lambda_name, payload)

        if success:
            current_app.logger.info(
                f"Successfully invoked log upload Lambda for broadcast {broadcast.reference}",
                extra={"broadcast_reference": broadcast.reference, "broadcast_event_id": broadcast_event_id},
            )
        else:
            current_app.logger.error(
                f"Failed to invoke log upload Lambda for broadcast {broadcast.reference}",
                extra={"broadcast_reference": broadcast.reference, "broadcast_event_id": broadcast_event_id},
            )

        return success

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


def _get_mno_details(broadcast):
    """
    Build the MNOs list with their IDs and contact emails
    """
    mnos = []

    # Get the providers used for this broadcast
    for provider in broadcast.broadcast_provider_messages:
        mno_info = {"mno_id": provider.provider_id, "emails": _get_mno_contact_emails(provider.provider_id)}
        mnos.append(mno_info)

    return mnos


def _get_mno_contact_emails(provider_id):
    """
    Get contact emails for a specific MNO/provider
    You'll need to determine where these are stored - perhaps in your database
    or config
    """
    # TODO: Hardcode placeholder for testing

    # Placeholder example:
    mno_contacts = current_app.config.get("MNO_CONTACT_EMAILS", {})
    return mno_contacts.get(provider_id, [])


def _invoke_log_upload_lambda(lambda_name, payload):
    """
    Invoke the log upload Lambda function
    """
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
                extra={
                    "status_code": response["StatusCode"],
                },
            )
            return True
        else:
            current_app.logger.error(
                f"Error invoking log upload lambda {lambda_name}",
                extra={
                    "status_code": response["StatusCode"],
                },
            )
            return False

    except botocore.exceptions.ClientError as e:
        current_app.logger.error(
            f"Boto3 ClientError calling log upload lambda {lambda_name}",
            extra={
                "python_module": __name__,
                "error": str(e),
            },
        )
        return False

    except Exception as e:
        current_app.logger.error(
            f"Unexpected error calling log upload lambda {lambda_name}",
            extra={
                "python_module": __name__,
                "error": str(e),
            },
        )
        return False
