import logging

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
        Optimized for a small number of To/Cc recipients and a large, chunked Bcc list.
        """
        to_addresses = to_addresses or []
        cc_addresses = cc_addresses or []
        bcc_addresses = bcc_addresses or []
        attachments = attachments or []

        # Build the Body structure
        body_content = {}
        if text_body:
            body_content["Text"] = {"Data": text_body, "Charset": "UTF-8"}
        if html_body:
            body_content["Html"] = {"Data": html_body, "Charset": "UTF-8"}

        # Format attachments for the SESv2 Simple schema
        ses_attachments = []
        for filename, file_bytes, mime_type in attachments:
            attachment_structure = {"RawContent": file_bytes, "FileName": filename}
            if mime_type:
                attachment_structure["ContentType"] = mime_type
            ses_attachments.append(attachment_structure)

        # Construct Simple message payload
        simple_message = {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body_content}

        if ses_attachments:
            simple_message["Attachments"] = ses_attachments

        # Chunk the BCC list to respect the 50 maximum recipient limit
        # First batch budget accommodates any To and Cc addresses
        fixed_recipients_count = len(to_addresses) + len(cc_addresses)
        initial_bcc_batch_size = max(1, 50 - fixed_recipients_count)

        bcc_batches = []
        # Slice out the first batch based on available remaining space
        if bcc_addresses:
            bcc_batches.append(bcc_addresses[:initial_bcc_batch_size])
            # Remaining BCCs are chunked cleanly into blocks of 50
            remaining_bcc = bcc_addresses[initial_bcc_batch_size:]
            for i in range(0, len(remaining_bcc), 50):
                bcc_batches.append(remaining_bcc[i : i + 50])
        else:
            # If there are absolutely no BCCs, create a single empty iteration
            # just to process the To/Cc addresses.
            bcc_batches = [[]]

        results = []

        try:
            for idx, bcc_batch in enumerate(bcc_batches):
                destination = {}

                # Only attach To and Cc to the very first batch
                # to avoid spamming them with duplicate emails.
                if idx == 0:
                    if to_addresses:
                        destination["ToAddresses"] = to_addresses
                    if cc_addresses:
                        destination["CcAddresses"] = cc_addresses

                if bcc_batch:
                    destination["BccAddresses"] = bcc_batch

                # Safely skip if an edge case creates a completely blank destination block
                if not destination:
                    continue

                # Send email, if enabled (ssev2 not supported in localstack envs)
                if self.send_enabled:
                    response = self.client.send_email(
                        FromEmailAddress=self.sender, Destination=destination, Content={"Simple": simple_message}
                    )
                    batch_total = len(bcc_batch) + (fixed_recipients_count if idx == 0 else 0)
                    results.append(
                        {
                            "batch_index": idx,
                            "batch_size": batch_total,
                            "message_id": response.get("MessageId"),
                            "status": "sent",
                        }
                    )
                    logger.info(
                        f"EmailClient.send_email batch {idx} sent to {batch_total} "
                        f"recipients (BCC chunk size: {len(bcc_batch)}) with message_id {response.get('MessageId')}"
                    )
                else:
                    batch_total = len(bcc_batch) + (fixed_recipients_count if idx == 0 else 0)
                    mock_id = f"localstack_{idx}"
                    results.append(
                        {"batch_index": idx, "batch_size": batch_total, "message_id": mock_id, "status": "sent"}
                    )
                    logger.info(
                        f"EmailClient.send_email would be sending batch {idx} to {batch_total} "
                        f"recipients (BCC chunk size: {len(bcc_batch)}) with message_id {mock_id}"
                    )

            return results

        except botocore.exceptions.ClientError as e:
            logger.error(f"EmailClient.send_email failed: {e.response['Error']}")
            raise
