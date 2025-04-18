import os
import uuid

import pytest
from emergency_alerts_utils.url_safe_token import generate_token
from flask import current_app, json
from freezegun import freeze_time

from tests import create_admin_authorization_header
from tests.app.db import create_invited_org_user


@pytest.mark.parametrize(
    "platform_admin_capable, expected_invited_by", ((True, "The GOV.UK Emergency Alerts team"), (False, "Test User"))
)
@pytest.mark.parametrize(
    "extra_args, expected_start_of_invite_url",
    [
        ({}, f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk"),
        ({"invite_link_host": "https://www.example.com"}, "https://www.example.com"),
    ],
)
def test_create_invited_org_user(
    admin_request,
    sample_organisation,
    sample_user,
    mocker,
    platform_admin_capable,
    expected_invited_by,
    expected_start_of_invite_url,
    extra_args,
):
    mocked = mocker.patch("app.organisation.invite_rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.organisation.invite_rest.generate_token", return_value=fake_token)
    email_address = "invited_user@example.com"
    sample_user.platform_admin_capable = platform_admin_capable

    data = dict(
        organisation=str(sample_organisation.id),
        email_address=email_address,
        invited_by=str(sample_user.id),
        **extra_args,
    )

    json_resp = admin_request.post(
        "organisation_invite.invite_user_to_org",
        organisation_id=sample_organisation.id,
        _data=data,
        _expected_status=201,
    )

    assert json_resp["data"]["email_address"] == email_address
    assert json_resp["data"]["invited_by"] == str(sample_user.id)
    assert json_resp["data"]["organisation"] == str(sample_organisation.id)

    notification = {
        "type": "email",
        "template_id": current_app.config["ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID"],
        "recipient": email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "user_name": expected_invited_by,
            "organisation_name": sample_organisation.name,
            "url": f"{expected_start_of_invite_url}/organisation-invitation/{fake_token}",
        },
    }

    mocked.assert_called_once_with(notification)


def test_create_invited_user_invalid_email(admin_request, sample_organisation, sample_user, mocker):
    mocked = mocker.patch("app.organisation.invite_rest.notify_send")
    email_address = "notanemail"

    data = {
        "service": str(sample_organisation.id),
        "email_address": email_address,
        "invited_by": str(sample_user.id),
    }

    json_resp = admin_request.post(
        "organisation_invite.invite_user_to_org",
        organisation_id=sample_organisation.id,
        _data=data,
        _expected_status=400,
    )

    assert json_resp["errors"][0]["message"] == "email_address Not a valid email address"
    assert mocked.call_count == 0


def test_get_all_invited_users_by_service(admin_request, sample_organisation, sample_user):
    for i in range(5):
        create_invited_org_user(
            sample_organisation, sample_user, email_address="invited_user_{}@service.gov.uk".format(i)
        )

    json_resp = admin_request.get(
        "organisation_invite.get_invited_org_users_by_organisation", organisation_id=sample_organisation.id
    )

    assert len(json_resp["data"]) == 5
    for invite in json_resp["data"]:
        assert invite["organisation"] == str(sample_organisation.id)
        assert invite["invited_by"] == str(sample_user.id)
        assert invite["id"]


def test_get_invited_users_by_service_with_no_invites(admin_request, sample_organisation):
    json_resp = admin_request.get(
        "organisation_invite.get_invited_org_users_by_organisation", organisation_id=sample_organisation.id
    )
    assert len(json_resp["data"]) == 0


def test_get_invited_user_by_organisation(admin_request, sample_invited_org_user):
    json_resp = admin_request.get(
        "organisation_invite.get_invited_org_user_by_organisation",
        organisation_id=sample_invited_org_user.organisation.id,
        invited_org_user_id=sample_invited_org_user.id,
    )
    assert json_resp["data"]["email_address"] == sample_invited_org_user.email_address


def test_get_invited_user_by_organisation_when_user_does_not_belong_to_the_org(
    admin_request,
    sample_invited_org_user,
    fake_uuid,
):
    json_resp = admin_request.get(
        "organisation_invite.get_invited_org_user_by_organisation",
        organisation_id=fake_uuid,
        invited_org_user_id=sample_invited_org_user.id,
        _expected_status=404,
    )
    assert json_resp["result"] == "error"


def test_update_org_invited_user_set_status_to_cancelled(admin_request, sample_invited_org_user):
    data = {"status": "cancelled"}

    json_resp = admin_request.post(
        "organisation_invite.update_org_invite_status",
        organisation_id=sample_invited_org_user.organisation_id,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
    )
    assert json_resp["data"]["status"] == "cancelled"


def test_update_org_invited_user_for_wrong_service_returns_404(admin_request, sample_invited_org_user, fake_uuid):
    data = {"status": "cancelled"}

    json_resp = admin_request.post(
        "organisation_invite.update_org_invite_status",
        organisation_id=fake_uuid,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
        _expected_status=404,
    )
    assert json_resp["message"] == "No result found"


def test_update_org_invited_user_for_invalid_data_returns_400(admin_request, sample_invited_org_user):
    data = {"status": "garbage"}

    json_resp = admin_request.post(
        "organisation_invite.update_org_invite_status",
        organisation_id=sample_invited_org_user.organisation_id,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
        _expected_status=400,
    )
    assert len(json_resp["errors"]) == 1
    assert json_resp["errors"][0]["message"] == "status garbage is not one of [pending, accepted, cancelled]"


@pytest.mark.parametrize(
    "endpoint_format_str",
    [
        "/invite/organisation/{}",
        "/invite/organisation/check/{}",
    ],
)
def test_validate_invitation_token_returns_200_when_token_valid(client, sample_invited_org_user, endpoint_format_str):
    token = generate_token(
        str(sample_invited_org_user.id), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
    )

    url = endpoint_format_str.format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"] == sample_invited_org_user.serialize()


def test_validate_invitation_token_for_expired_token_returns_400(client):
    with freeze_time("2016-01-01T12:00:00"):
        token = generate_token(
            str(uuid.uuid4()), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
        )
    url = "/invite/organisation/{}".format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {
        "invitation": "Your invitation to GOV.UK Notify has expired. "
        "Please ask the person that invited you to send you another one"
    }


def test_validate_invitation_token_returns_400_when_invited_user_does_not_exist(client):
    token = generate_token(str(uuid.uuid4()), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])
    url = "/invite/organisation/{}".format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_validate_invitation_token_returns_400_when_token_is_malformed(client):
    token = generate_token(str(uuid.uuid4()), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])[
        :-2
    ]

    url = "/invite/organisation/{}".format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {
        "invitation": "Something’s wrong with this link. Make sure you’ve copied the whole thing."
    }


def test_get_invited_org_user(admin_request, sample_invited_org_user):
    json_resp = admin_request.get(
        "organisation_invite.get_invited_org_user", invited_org_user_id=sample_invited_org_user.id
    )
    assert json_resp["data"]["id"] == str(sample_invited_org_user.id)
    assert json_resp["data"]["email_address"] == sample_invited_org_user.email_address
    assert json_resp["data"]["organisation"] == str(sample_invited_org_user.organisation_id)


def test_get_invited_org_user_404s_if_invite_doesnt_exist(admin_request, sample_invited_org_user, fake_uuid):
    json_resp = admin_request.get(
        "organisation_invite.get_invited_org_user", invited_org_user_id=fake_uuid, _expected_status=404
    )
    assert json_resp["result"] == "error"
