import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from flask import current_app, url_for
from freezegun import freeze_time

from app import db
from app.dao.users_dao import create_user_code
from app.models import EMAIL_TYPE, SMS_TYPE, USER_AUTH_TYPES, User, VerifyCode
from tests import create_admin_authorization_header


@freeze_time("2016-01-01T12:00:00")
def test_user_verify_sms_code(client, sample_sms_code):
    sample_sms_code.user.logged_in_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert not VerifyCode.query.first().code_used
    assert sample_sms_code.user.current_session_id is None
    data = json.dumps({"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert VerifyCode.query.first().code_used
    assert sample_sms_code.user.logged_in_at == datetime.now()
    assert sample_sms_code.user.email_access_validated_at != datetime.now()
    assert sample_sms_code.user.current_session_id is not None


def test_user_verify_code_missing_code(client, sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({"code_type": sample_sms_code.code_type})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 0


def test_user_verify_code_bad_code_and_increments_failed_login_count(client, sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({"code_type": sample_sms_code.code_type, "code": "blah"})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 404
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 1


@pytest.mark.parametrize(
    "failed_login_count, expected_status",
    (
        (9, 204),
        (10, 404),
    ),
)
def test_user_verify_code_rejects_good_code_if_too_many_failed_logins(
    client,
    sample_sms_code,
    failed_login_count,
    expected_status,
):
    sample_sms_code.user.failed_login_count = failed_login_count
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=json.dumps(
            {
                "code_type": sample_sms_code.code_type,
                "code": sample_sms_code.txt_code,
            }
        ),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert resp.status_code == expected_status


@freeze_time("2020-04-01 12:00")
@pytest.mark.parametrize("code_type", [EMAIL_TYPE, SMS_TYPE])
def test_user_verify_code_expired_code_and_increments_failed_login_count(code_type, admin_request, sample_user):
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, code_type)
    verify_code.expiry_datetime = datetime(2020, 4, 1, 11, 59)

    data = {"code_type": code_type, "code": magic_code}

    admin_request.post("user.verify_user_code", user_id=sample_user.id, _data=data, _expected_status=400)

    assert verify_code.code_used is False
    assert sample_user.logged_in_at is None
    assert sample_user.current_session_id is None
    assert sample_user.failed_login_count == 1


@freeze_time("2016-01-01 10:00:00.000000")
def test_user_verify_password(client, sample_user):
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    sample_user.logged_in_at = yesterday
    data = json.dumps({"password": "password"})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert User.query.get(sample_user.id).logged_in_at == yesterday


def test_user_verify_password_invalid_password(client, sample_user):
    data = json.dumps({"password": "bad password"})
    auth_header = create_admin_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert "Incorrect password" in json_resp["message"]["password"]
    assert sample_user.failed_login_count == 1


def test_user_verify_password_valid_password_resets_failed_logins(client, sample_user):
    with freeze_time("2015-01-01T00:00:00") as the_time:
        data = json.dumps({"password": "bad password"})
        auth_header = create_admin_authorization_header()

        assert sample_user.failed_login_count == 0

        resp = client.post(
            url_for("user.verify_user_password", user_id=sample_user.id),
            data=data,
            headers=[("Content-Type", "application/json"), auth_header],
        )
        assert resp.status_code == 400
        json_resp = json.loads(resp.get_data(as_text=True))
        assert "Incorrect password" in json_resp["message"]["password"]

        assert sample_user.failed_login_count == 1

        the_time.tick(timedelta(minutes=1))  # To ensure the new login attempt is not throttled

        data = json.dumps({"password": "password"})
        auth_header = create_admin_authorization_header()
        resp = client.post(
            url_for("user.verify_user_password", user_id=sample_user.id),
            data=data,
            headers=[("Content-Type", "application/json"), auth_header],
        )

        assert resp.status_code == 204
        assert sample_user.failed_login_count == 0


def test_user_verify_password_missing_password(client, sample_user):
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=json.dumps({"bingo": "bongo"}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert "Required field missing data" in json_resp["message"]["password"]


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_sms_code(client, sample_user, mocker):
    auth_header = create_admin_authorization_header()
    mock_create_secret_code = mocker.patch("app.user.rest.create_secret_code", return_value="11111")
    mock_notify_send = mocker.patch("app.user.rest.notify_send")

    resp = client.post(
        url_for("user.send_user_2fa_code", code_type="sms", user_id=sample_user.id),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204

    assert mock_create_secret_code.call_count == 1
    assert VerifyCode.query.one().check_code("11111")

    notification = {
        "type": "sms",
        "template_id": current_app.config["SMS_CODE_TEMPLATE_ID"],
        "recipient": sample_user.mobile_number,
        "reply_to": None,
        "personalisation": {"verify_code": "11111"},
    }

    mock_notify_send.assert_called_once_with(notification)


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_code_for_sms_with_optional_to_field(client, sample_user, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code with optional to field
    """
    to_number = "+447119876757"
    mock_create_secret_code = mocker.patch("app.user.rest.create_secret_code", return_value="11111")
    mock_notify_send = mocker.patch("app.user.rest.notify_send")
    auth_header = create_admin_authorization_header()

    resp = client.post(
        url_for("user.send_user_2fa_code", code_type="sms", user_id=sample_user.id),
        data=json.dumps({"to": to_number}),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert resp.status_code == 204
    assert mock_create_secret_code.call_count == 1

    notification = {
        "type": "sms",
        "template_id": current_app.config["SMS_CODE_TEMPLATE_ID"],
        "recipient": to_number,
        "reply_to": None,
        "personalisation": {"verify_code": "11111"},
    }

    mock_notify_send.assert_called_once_with(notification)


def test_send_sms_code_returns_404_for_bad_input_data(client):
    uuid_ = uuid.uuid4()
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_user_2fa_code", code_type="sms", user_id=uuid_),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))["message"] == "No result found"


def test_send_sms_code_returns_204_when_too_many_codes_already_created(client, sample_user):
    for _ in range(5):
        verify_code = VerifyCode(
            code_type="sms",
            _code=12345,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            expiry_datetime=datetime.now(timezone.utc) + timedelta(minutes=40),
            user=sample_user,
        )
        db.session.add(verify_code)
        db.session.commit()
    assert VerifyCode.query.count() == 5
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_user_2fa_code", code_type="sms", user_id=sample_user.id),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert VerifyCode.query.count() == 5


@pytest.mark.parametrize(
    "post_data, expected_url_starts_with",
    (
        (
            {},
            f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk",
        ),
        (
            {"admin_base_url": "https://example.com"},
            "https://example.com",
        ),
    ),
)
def test_send_new_user_email_verification(
    client,
    sample_user,
    mocker,
    post_data,
    expected_url_starts_with,
):
    mock_notify_send = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_new_user_email_verification", user_id=str(sample_user.id)),
        data=json.dumps(post_data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert VerifyCode.query.count() == 0

    notification = {
        "type": "email",
        "template_id": current_app.config["NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {"name": "Test User", "url": expected_url_starts_with + "/verify-email/" + "0123456789"},
    }

    mock_notify_send.assert_called_once_with(notification)


def test_send_email_verification_returns_404_for_bad_input_data(client, notify_db_session, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code return 404 for bad input data
    """
    mock_notify_send = mocker.patch("app.user.rest.notify_send")

    uuid_ = uuid.uuid4()
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_new_user_email_verification", user_id=uuid_),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))["message"] == "No result found"
    assert mock_notify_send.call_count == 0


def test_user_verify_user_code_returns_404_when_code_is_right_but_user_account_is_locked(client, sample_sms_code):
    sample_sms_code.user.failed_login_count = 10
    data = json.dumps({"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code})
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert resp.status_code == 404
    assert sample_sms_code.user.failed_login_count == 10
    assert not sample_sms_code.code_used


def test_user_verify_user_code_returns_429_when_user_is_throttled(client, sample_sms_code):
    incorrect_code = json.dumps({"code_type": sample_sms_code.code_type, "code": "12345"})
    correct_code = json.dumps({"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code})
    client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=incorrect_code,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=incorrect_code,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=correct_code,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert resp.status_code == 429
    assert not sample_sms_code.code_used


def test_user_verify_user_code_returns_204_after_throttle_period(client, sample_sms_code):
    incorrect_code = json.dumps({"code_type": sample_sms_code.code_type, "code": "12345"})
    correct_code = json.dumps({"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code})
    with freeze_time("2015-01-01T00:00:00") as the_time:
        client.post(
            url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
            data=incorrect_code,
            headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
        )
        client.post(
            url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
            data=incorrect_code,
            headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
        )
        resp_2 = client.post(
            url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
            data=correct_code,
            headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
        )
        the_time.tick(timedelta(minutes=1))
        resp_3 = client.post(
            url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
            data=correct_code,
            headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
        )
        assert resp_2.status_code == 429
        assert resp_3.status_code == 204
        assert sample_sms_code.code_used


def test_user_verify_user_code_valid_code_resets_failed_login_count(client, sample_sms_code):
    sample_sms_code.user.failed_login_count = 1
    data = json.dumps({"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code})
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert resp.status_code == 204
    assert sample_sms_code.user.failed_login_count == 0
    assert sample_sms_code.code_used


def test_user_reset_failed_login_count_returns_200(client, sample_user):
    sample_user.failed_login_count = 1
    resp = client.post(
        url_for("user.user_reset_failed_login_count", user_id=sample_user.id),
        data={},
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert resp.status_code == 200
    assert sample_user.failed_login_count == 0


def test_reset_failed_login_count_returns_404_when_user_does_not_exist(client):
    resp = client.post(
        url_for("user.user_reset_failed_login_count", user_id=uuid.uuid4()),
        data={},
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert resp.status_code == 404


# we send sms_auth users and webauthn_auth users email code to validate their email access
@pytest.mark.parametrize("auth_type", USER_AUTH_TYPES)
@pytest.mark.parametrize(
    "data, expected_auth_url",
    (
        (
            {},
            f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk/email-auth/",
        ),
        (
            {"to": None},
            f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk/email-auth/",
        ),
        (
            {"to": None, "email_auth_link_host": "https://example.com"},
            "https://example.com/email-auth/",
        ),
    ),
)
def test_send_user_email_code(admin_request, mocker, sample_user, data, expected_auth_url, auth_type):
    mock_notify_send = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)
    sample_user.auth_type = auth_type

    admin_request.post(
        "user.send_user_2fa_code", code_type="email", user_id=sample_user.id, _data=data, _expected_status=204
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["EMAIL_2FA_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "personalisation": {
            "name": "Test User",
            "url": expected_auth_url + fake_token,
        },
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
    }

    mock_notify_send.assert_called_once_with(notification)


def test_send_user_email_code_with_urlencoded_next_param(admin_request, mocker, sample_user):
    mock_notify_send = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)

    data = {"to": None, "next": "/services"}
    admin_request.post(
        "user.send_user_2fa_code", code_type="email", user_id=sample_user.id, _data=data, _expected_status=204
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["EMAIL_2FA_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "name": "Test User",
            "url": f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk/email-auth/"
            + fake_token
            + "?next=%2Fservices",
        },
    }

    mock_notify_send.assert_called_once_with(notification)


def test_send_email_code_returns_404_for_bad_input_data(admin_request):
    resp = admin_request.post(
        "user.send_user_2fa_code", code_type="email", user_id=uuid.uuid4(), _data={}, _expected_status=404
    )
    assert resp["message"] == "No result found"


@freeze_time("2016-01-01T12:00:00")
# we send sms_auth and webauthn_auth users email code to validate their email access
@pytest.mark.parametrize("auth_type", USER_AUTH_TYPES)
def test_user_verify_email_code(admin_request, sample_user, auth_type):
    sample_user.logged_in_at = datetime.now(timezone.utc) - timedelta(days=1)
    sample_user.email_access_validated_at = datetime.now(timezone.utc) - timedelta(days=1)
    sample_user.auth_type = auth_type
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, EMAIL_TYPE)

    data = {"code_type": "email", "code": magic_code}

    admin_request.post("user.verify_user_code", user_id=sample_user.id, _data=data, _expected_status=204)

    assert verify_code.code_used
    assert sample_user.logged_in_at == datetime.now()
    assert sample_user.email_access_validated_at == datetime.now()
    assert sample_user.current_session_id is not None


@pytest.mark.parametrize("code_type", [EMAIL_TYPE, SMS_TYPE])
@freeze_time("2016-01-01T12:00:00")
def test_user_verify_email_code_fails_if_code_already_used(admin_request, sample_user, code_type):
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, code_type)
    verify_code.code_used = True

    data = {"code_type": code_type, "code": magic_code}

    admin_request.post("user.verify_user_code", user_id=sample_user.id, _data=data, _expected_status=400)

    assert verify_code.code_used
    assert sample_user.logged_in_at is None
    assert sample_user.current_session_id is None


def test_send_user_2fa_code_sends_from_number_for_international_numbers(client, sample_user, mocker):
    sample_user.mobile_number = "601117224412"
    auth_header = create_admin_authorization_header()
    mocker.patch("app.user.rest.create_secret_code", return_value="11111")
    mock_notify_send = mocker.patch("app.user.rest.notify_send")

    resp = client.post(
        url_for("user.send_user_2fa_code", code_type="sms", user_id=sample_user.id),
        data=json.dumps({"to": sample_user.mobile_number}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204

    notification = {
        "type": "sms",
        "template_id": current_app.config["SMS_CODE_TEMPLATE_ID"],
        "recipient": sample_user.mobile_number,
        "personalisation": {"verify_code": "11111"},
        "reply_to": None,
    }

    mock_notify_send.assert_called_once_with(notification)
