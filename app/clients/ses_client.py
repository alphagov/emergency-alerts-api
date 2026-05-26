import logging
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
import botocore.exceptions

from app.utils import is_local_host, is_local_stack

logger = logging.getLogger(__name__)


class SESClient:
    def __init__(self, client=None, sender=None):

        if is_local_stack() or is_local_host():
            endpoint = os.environ.get("AWS_ENDPOINT_URL_SES", "http://localstack:4566")
            from_address = "support@localhost"
            aws_region = "us-east-1"
        else:
            endpoint = None
            from_address = os.environ.get("SES_FROM_EMAIL_ADDRESS", "support@localhost")
            aws_region = os.environ.get("AWS_REGION", "eu-west-2")

        self.client = client or boto3.client("ses", region_name=aws_region, endpoint_url=endpoint)
        self.sender = sender or from_address

    def send_email(self, to, subject, body_text=None, body_html=None):
        """
        Sends an email via AWS SES.
        Supports both text and HTML bodies.
        """

        if is_local_host():
            logger.info("Local environment — skipping SES send")
            return {"status": "skipped-local"}

        if not body_text and not body_html:
            raise ValueError("Must provide at least one of body_text or body_html")

        message = {
            "Subject": {"Data": subject},
            "Body": {},
        }

        if body_text:
            message["Body"]["Text"] = {"Data": body_text}

        if body_html:
            message["Body"]["Html"] = {"Data": body_html}

        try:
            response = self.client.send_email(
                Source=self.sender,
                Destination={"ToAddresses": to},
                Message=message,
            )
            logger.info(f"SES email sent to {to}")
            return response

        except botocore.exceptions.ClientError as e:
            logger.error(f"SES send_email failed: {e.response['Error']}")
            raise

    def send_raw_email(self, subject, html_body, to_addresses, attachments=None):
        """
        Send an email with optional attachments using SES send_raw_email.
        attachments: list of tuples -> [("file.txt", b"content"), ...]
        """

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(to_addresses)

        # Add HTML body
        msg.attach(MIMEText(html_body, "html"))

        # Add attachments
        if attachments:
            for filename, file_bytes, mime_type in attachments:
                part = _build_mime_attachment(filename, file_bytes, mime_type)
                msg.attach(part)

        # Send via SES
        try:
            response = self.client.send_raw_email(RawMessage={"Data": msg.as_string()})

            return response
        except botocore.exceptions.ClientError as e:
            logger.error(f"SES send_raw_email failed: {e.response['Error']}")
            raise


def _build_mime_attachment(filename, file_bytes, mime_type):
    maintype, subtype = mime_type.split("/")

    part = MIMEBase(maintype, subtype)
    part.set_payload(file_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=filename)

    return part
