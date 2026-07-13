# conftest.py
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.errors import InvalidRequest


@pytest.fixture
def email_client_fixture():
    """
    Patches flask.current_app BEFORE importing EmailClient.
    Provides a fake boto client and returns (EmailClient, fake_client, fake_app).
    """
    fake_app = MagicMock()
    fake_app.config = {
        "SES_ENDPOINT": "http://example.com",
        "SES_FROM_ADDRESS": "sender@example.com",
        "SES_REGION": "eu-west-1",
        "SES_ENABLED": True,
    }

    fake_boto_client = MagicMock()

    with patch("app.clients.email_client.current_app", fake_app), patch(
        "app.clients.email_client.boto3.client", return_value=fake_boto_client
    ):

        from app.clients.email_client import EmailClient

        yield EmailClient, fake_boto_client, fake_app


def test_constructor_missing_from_address(email_client_fixture):
    EmailClient, _, fake_app = email_client_fixture

    fake_app.config["SES_FROM_ADDRESS"] = None

    with pytest.raises(InvalidRequest):
        EmailClient()


def test_send_email_simple_no_bcc(email_client_fixture):
    EmailClient, fake_boto, _ = email_client_fixture

    client = EmailClient()

    result = client.send_email(
        subject="Hello",
        text_body="Plain",
        html_body="<p>HTML</p>",
        to_addresses=["a@example.com"],
        cc_addresses=["b@example.com"],
        bcc_addresses=[],
    )

    # Should produce exactly one batch
    assert len(result) == 1
    batch = result[0]
    assert batch["batch_index"] == 0
    assert batch["batch_size"] == 2  # To + Cc

    # Inspect boto call
    fake_boto.send_email.assert_called_once()
    args, kwargs = fake_boto.send_email.call_args

    assert kwargs["Destination"]["ToAddresses"] == ["a@example.com"]
    assert kwargs["Destination"]["CcAddresses"] == ["b@example.com"]
    assert "BccAddresses" not in kwargs["Destination"]


def test_send_email_bcc_batching(email_client_fixture):
    EmailClient, fake_boto, _ = email_client_fixture

    client = EmailClient()

    bcc = [f"user{i}@example.com" for i in range(120)]  # 120 → 3 batches (50, 50, 20)

    result = client.send_email(
        subject="Batch Test",
        text_body="Body",
        html_body=None,
        to_addresses=["to@example.com"],
        cc_addresses=[],
        bcc_addresses=bcc,
    )

    assert len(result) == 3

    # Batch 0: To + first 49 BCC (50 total limit)
    assert result[0]["batch_index"] == 0
    assert result[0]["batch_size"] == 50

    # Batch 1: next 50 BCC
    assert result[1]["batch_size"] == 50

    # Batch 2: remaining 20 BCC
    assert result[2]["batch_size"] == 21

    # boto called 3 times
    assert fake_boto.send_email.call_count == 3

    # Inspect first call
    _, kwargs0 = fake_boto.send_email.call_args_list[0]
    assert kwargs0["Destination"]["ToAddresses"] == ["to@example.com"]
    assert len(kwargs0["Destination"]["BccAddresses"]) == 49


def test_send_email_mixed_recipients(email_client_fixture):
    EmailClient, fake_boto, _ = email_client_fixture

    client = EmailClient()

    to = ["to1@example.com", "to2@example.com"]
    cc = ["cc@example.com"]
    bcc = [f"user{i}@example.com" for i in range(60)]

    # fixed recipients = 3 → first batch BCC capacity = 47
    result = client.send_email(
        subject="Mixed",
        text_body="Body",
        html_body=None,
        to_addresses=to,
        cc_addresses=cc,
        bcc_addresses=bcc,
    )

    assert len(result) == 2

    # Batch 0: 3 fixed + 47 BCC = 50
    assert result[0]["batch_size"] == 50

    # Batch 1: remaining 13 BCC
    assert result[1]["batch_size"] == 13

    # Inspect first call
    _, kwargs0 = fake_boto.send_email.call_args_list[0]
    assert kwargs0["Destination"]["ToAddresses"] == to
    assert kwargs0["Destination"]["CcAddresses"] == cc
    assert len(kwargs0["Destination"]["BccAddresses"]) == 47

    # Second call: no To/Cc
    _, kwargs1 = fake_boto.send_email.call_args_list[1]
    assert "ToAddresses" not in kwargs1["Destination"]
    assert "CcAddresses" not in kwargs1["Destination"]
    assert len(kwargs1["Destination"]["BccAddresses"]) == 13


def test_send_email_attachments(email_client_fixture):
    EmailClient, fake_boto, _ = email_client_fixture

    client = EmailClient()

    attachments = [
        ("file1.txt", b"hello", "text/plain"),
        ("file2.bin", b"\x00\x01", None),
    ]

    client.send_email(
        subject="Attach",
        text_body="Body",
        html_body=None,
        to_addresses=["to@example.com"],
        attachments=attachments,
    )

    _, kwargs = fake_boto.send_email.call_args

    simple = kwargs["Content"]["Simple"]
    assert "Attachments" in simple
    assert len(simple["Attachments"]) == 2

    a1 = simple["Attachments"][0]
    assert a1["FileName"] == "file1.txt"
    assert a1["RawContent"] == b"hello"
    assert a1["ContentType"] == "text/plain"

    a2 = simple["Attachments"][1]
    assert a2["FileName"] == "file2.bin"
    assert a2["RawContent"] == b"\x00\x01"
    assert "ContentType" not in a2


def test_send_email_disabled_mode(email_client_fixture):
    EmailClient, fake_boto, fake_app = email_client_fixture

    fake_app.config["SES_ENABLED"] = False
    client = EmailClient()

    result = client.send_email(
        subject="Disabled",
        text_body="Body",
        html_body=None,
        to_addresses=["to@example.com"],
        bcc_addresses=["bcc@example.com"],
    )

    # Should produce one batch
    assert len(result) == 1
    batch = result[0]
    assert batch["message_id"] == "localstack_0"
    assert batch["status"] == "sent"

    # boto should NOT be called
    fake_boto.send_email.assert_not_called()


def test_send_email_boto_error(email_client_fixture):
    EmailClient, fake_boto, _ = email_client_fixture

    fake_boto.send_email.side_effect = ClientError({"Error": {"Code": "Boom", "Message": "Failure"}}, "send_email")

    client = EmailClient()

    with pytest.raises(ClientError):
        client.send_email(
            subject="Err",
            text_body="Body",
            html_body=None,
            to_addresses=["to@example.com"],
        )
