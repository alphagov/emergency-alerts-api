import logging
from email import encoders
from email.mime.base import MIMEBase

import boto3
import botocore.exceptions
from flask import current_app

from app.errors import InvalidRequest

logger = logging.getLogger(__name__)


class EmailClient:
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

        # Localstack does not support sesv2 so only enable if config allows it
        self.send_enabled = current_app.config["SES_ENABLED"]

    def send_email(
        self, subject, text_body, html_body, to_addresses=None, cc_addresses=None, bcc_addresses=None, attachments=None
    ):
        """
        Send an email with optional attachments using SESv2 Simple content structure.
        """
        to_addresses = to_addresses or []
        cc_addresses = cc_addresses or []
        bcc_addresses = bcc_addresses or []
        attachments = attachments or []

        # Build the Destination object
        destination = {}
        if to_addresses:
            destination["ToAddresses"] = to_addresses
        if cc_addresses:
            destination["CcAddresses"] = cc_addresses
        if bcc_addresses:
            destination["BccAddresses"] = bcc_addresses

        # Build the Body structure
        body_content = {}
        if text_body:
            body_content["Text"] = {"Data": text_body, "Charset": "UTF-8"}
        if html_body:
            body_content["Html"] = {"Data": html_body, "Charset": "UTF-8"}

        # Format attachments for the SESv2 Simple schema
        ses_attachments = []
        for filename, file_bytes, mime_type in attachments:
            attachment_structure = {
                "RawContent": file_bytes,  # Boto3 handles the underlying serialization of bytes
                "FileName": filename,
            }
            if mime_type:
                attachment_structure["ContentType"] = mime_type

            ses_attachments.append(attachment_structure)

        # Construct Simple message payload
        simple_message = {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body_content}

        if ses_attachments:
            simple_message["Attachments"] = ses_attachments

        # Execute the SESv2 send call
        try:
            if self.send_enabled:
                response = self.client.send_email(
                    FromEmailAddress=self.sender, Destination=destination, Content={"Simple": simple_message}
                )
                logger.info(f"EmailClient.send_email sent successfully with message_id {response.get('MessageId')}")
                return [{"message_id": response.get("MessageId"), "status": "sent"}]
            else:
                logger.info(f"EmailClient - localstack would be sending from {self.sender} to {destination} ")
                return [{"message_id": "localstack", "status": "sent"}]

        except botocore.exceptions.ClientError as e:
            logger.error(f"EmailClient.send_email failed: {e.response['Error']}")
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
