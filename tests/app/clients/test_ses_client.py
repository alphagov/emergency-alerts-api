from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_current_app():
    fake = SimpleNamespace(
        config={
            "SES_ENDPOINT": "http://example.com",
            "SES_FROM_ADDRESS": "sender@example.com",
            "SES_REGION": "eu-west-1",
        }
    )
    return fake


def test_sesclient_initialises_correctly(fake_current_app):
    with patch("flask.current_app", fake_current_app):
        from app.clients.ses_client import SESClient

        mock_client = MagicMock()
        ses = SESClient(client=mock_client)

        assert ses.client is mock_client
        assert ses.sender == "sender@example.com"


def test_sesclient_batches(fake_current_app):
    with patch("flask.current_app", fake_current_app):
        from app.clients.ses_client import SESClient

        to_addrs = [f"user{i}@example.com" for i in range(120)]
        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "mock-id"}

        ses = SESClient(client=mock_client)

        results = ses.send_email(
            subject="Test",
            text_body="Plain",
            html_body="<p>HTML</p>",
            to_addresses=to_addrs,
        )

    assert len(results) == 3
    assert mock_client.send_email.call_count == 3

    calls = mock_client.send_email.call_args_list

    assert calls[0].kwargs["Destination"]["ToAddresses"] == to_addrs[:50]
    assert calls[1].kwargs["Destination"]["ToAddresses"] == to_addrs[50:100]
    assert calls[2].kwargs["Destination"]["ToAddresses"] == to_addrs[100:]


def test_mime_reused_across_batches(fake_current_app):
    with patch("flask.current_app", fake_current_app):
        from app.clients.ses_client import SESClient

        to_addrs = [f"user{i}@example.com" for i in range(120)]
        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "mock-id"}

        ses = SESClient(client=mock_client)

        ses.send_email(
            subject="Test",
            text_body="Plain",
            html_body="<p>HTML</p>",
            to_addresses=to_addrs,
        )

    calls = mock_client.send_email.call_args_list
    raw1 = calls[0].kwargs["Content"]["Raw"]["Data"]
    raw2 = calls[1].kwargs["Content"]["Raw"]["Data"]
    raw3 = calls[2].kwargs["Content"]["Raw"]["Data"]

    assert raw1 == raw2 == raw3


def test_bcc_header_is_removed(fake_current_app):
    with patch("flask.current_app", fake_current_app):
        from app.clients.ses_client import SESClient

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "mock-id"}

        ses = SESClient(client=mock_client)

        ses.send_email(
            subject="Test",
            text_body="Plain",
            html_body="<p>HTML</p>",
            to_addresses=["a@example.com"],
            bcc_addresses=["hidden@example.com"],
        )

    raw = mock_client.send_email.call_args.kwargs["Content"]["Raw"]["Data"]
    assert b"Bcc:" not in raw


def test_attachments_added_correctly(fake_current_app):
    with patch("flask.current_app", fake_current_app):
        import base64

        from app.clients.ses_client import SESClient

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "mock-id"}

        ses = SESClient(client=mock_client)

        ses.send_email(
            subject="Test",
            text_body="Plain",
            html_body="<p>HTML</p>",
            to_addresses=["a@example.com"],
            attachments=[("file.txt", b"hello", "text/plain")],
        )

    raw = mock_client.send_email.call_args.kwargs["Content"]["Raw"]["Data"]

    # filename appears in header
    assert b"file.txt" in raw

    # content is base64 encoded
    assert base64.b64encode(b"hello") in raw


def test_ses_errors_propagate(fake_current_app):
    with patch("flask.current_app", fake_current_app):
        import botocore.exceptions

        from app.clients.ses_client import SESClient

        mock_client = MagicMock()
        mock_client.send_email.side_effect = botocore.exceptions.ClientError(
            error_response={"Error": {"Code": "Boom"}},
            operation_name="SendEmail",
        )

        ses = SESClient(client=mock_client)

        with pytest.raises(botocore.exceptions.ClientError):
            ses.send_email(
                subject="Test",
                text_body="Plain",
                html_body="<p>HTML</p>",
                to_addresses=["a@example.com"],
            )
