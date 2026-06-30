import logging
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
import botocore.exceptions
from flask import current_app

from app.errors import InvalidRequest

logger = logging.getLogger(__name__)


class SESClient:
    def __init__(self, client=None, sender=None):

        endpoint = current_app.config["SES_ENDPOINT"]
        from_address = current_app.config["SES_FROM_ADDRESS"]
        if from_address is None:
            raise InvalidRequest(
                "SES_FROM_ADDRESS configuration variable not set",
                status_code=400,
            )
        aws_region = current_app.config["SES_REGION"]

        self.client = client or boto3.client("sesv2", region_name=aws_region, endpoint_url=endpoint)
        self.sender = sender or from_address

    def send_email(
        self, subject, text_body, html_body, to_addresses=None, cc_addresses=None, bcc_addresses=None, attachments=None
    ):
        """
        Send an email with optional attachments using SES send_email.
        attachments: list of tuples -> [("file.txt", b"content"), ...]
        """

        to_addresses = to_addresses or []
        cc_addresses = cc_addresses or []
        bcc_addresses = bcc_addresses or []

        # SES envelope recipients (this is what SES actually uses)
        recipients = to_addresses + cc_addresses + bcc_addresses

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(to_addresses) if to_addresses else "undisclosed-recipients:;"

        if cc_addresses:
            msg["Cc"] = ", ".join(cc_addresses)

        # Alternative block for text + HTML
        alt = MIMEMultipart("alternative")

        # Plain text part
        alt.attach(MIMEText(text_body, "plain", "utf-8"))

        # HTML part
        alt.attach(MIMEText(html_body, "html", "utf-8"))

        # Attach the alternative block to the main message
        msg.attach(alt)

        # Add attachments
        if attachments:
            for filename, file_bytes, mime_type in attachments:
                part = _build_mime_attachment(filename, file_bytes, mime_type)
                msg.attach(part)

        # Double check for Bcc and remove if present
        if "Bcc" in msg:
            del msg["Bcc"]

        # Send via SES.
        results = []
        try:
            # SES has a hard limit of 50 recipients per SES call.
            for batch in _batch_recipients(recipients, 50):
                response = self.client.send_email(
                    FromEmailAddress=self.sender,
                    Destination={"ToAddresses": batch},
                    Content={"Raw": {"Data": msg.as_string().encode("utf-8")}},
                )
                results.append(
                    {
                        "batch_size": len(batch),
                        "message_id": response.get("MessageId"),
                        "status": "sent",
                    }
                )
                logger.info(
                    f"SESClient.send_email sent to {len(batch)} recipients with message_id {response.get("MessageId")}"
                )
            return results
        except botocore.exceptions.ClientError as e:
            logger.error(f"SESClient.send_email failed: {e.response['Error']}")
            raise


def _build_mime_attachment(filename, file_bytes, mime_type):
    maintype, subtype = mime_type.split("/")

    part = MIMEBase(maintype, subtype)
    part.set_payload(file_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=filename)

    return part


def _batch_recipients(recipients, batchsize):
    """Yield successive chunks of up to `batchsize` recipients."""
    for i in range(0, len(recipients), batchsize):
        yield recipients[i : i + batchsize]
