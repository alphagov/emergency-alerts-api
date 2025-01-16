import os
import uuid
from datetime import datetime
from unittest import mock

import pytest
from flask import current_app
from freezegun import freeze_time

from app.dao.permissions_dao import default_service_permissions
from app.dao.service_user_dao import (
    dao_get_service_user,
    dao_update_service_user,
)
from app.models import (
    EMAIL_AUTH_TYPE,
    MANAGE_SETTINGS,
    MANAGE_TEMPLATES,
    SMS_AUTH_TYPE,
    CommonPasswords,
    Permission,
    User,
)
from tests.app.db import (
    create_organisation,
    create_service,
    create_template_folder,
    create_user,
    create_webauthn_credential,
)


def test_get_user_list(admin_request, sample_service):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    json_resp = admin_request.get("user.get_user")

    # it may have the notify user in the DB still :weary:
    assert len(json_resp["data"]) >= 1
    sample_user = sample_service.users[0]
    expected_permissions = default_service_permissions
    fetched = next(x for x in json_resp["data"] if x["id"] == str(sample_user.id))

    assert sample_user.name == fetched["name"]
    assert sample_user.mobile_number == fetched["mobile_number"]
    assert sample_user.email_address == fetched["email_address"]
    assert sample_user.state == fetched["state"]
    assert sorted(expected_permissions) == sorted(fetched["permissions"][str(sample_service.id)])


def test_get_user(admin_request, sample_service, sample_organisation):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    sample_user = sample_service.users[0]
    sample_user.organisations = [sample_organisation]
    json_resp = admin_request.get("user.get_user", user_id=sample_user.id)

    expected_permissions = default_service_permissions
    fetched = json_resp["data"]

    assert fetched["id"] == str(sample_user.id)
    assert fetched["name"] == sample_user.name
    assert fetched["mobile_number"] == sample_user.mobile_number
    assert fetched["email_address"] == sample_user.email_address
    assert fetched["state"] == sample_user.state
    assert fetched["auth_type"] == SMS_AUTH_TYPE
    assert fetched["permissions"].keys() == {str(sample_service.id)}
    assert fetched["services"] == [str(sample_service.id)]
    assert fetched["organisations"] == [str(sample_organisation.id)]
    assert fetched["can_use_webauthn"] is False
    assert sorted(fetched["permissions"][str(sample_service.id)]) == sorted(expected_permissions)


def test_get_user_doesnt_return_inactive_services_and_orgs(admin_request, sample_service, sample_organisation):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    sample_service.active = False
    sample_organisation.active = False

    sample_user = sample_service.users[0]
    sample_user.organisations = [sample_organisation]

    json_resp = admin_request.get("user.get_user", user_id=sample_user.id)

    fetched = json_resp["data"]

    assert fetched["id"] == str(sample_user.id)
    assert fetched["services"] == []
    assert fetched["organisations"] == []
    assert fetched["permissions"] == {}


def test_post_user(admin_request, notify_db_session):
    """
    Tests POST endpoint '/' to create a user.
    """
    User.query.delete()
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password123456",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
        "auth_type": EMAIL_AUTH_TYPE,
    }
    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=201)

    user = User.query.filter_by(email_address="user@digital.cabinet-office.gov.uk").first()
    assert user.check_password("password123456")
    assert json_resp["data"]["email_address"] == user.email_address
    assert json_resp["data"]["id"] == str(user.id)
    assert user.auth_type == EMAIL_AUTH_TYPE


def test_post_user_without_auth_type(admin_request, notify_db_session):
    User.query.delete()
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password123456",
        "mobile_number": "+447700900986",
        "permissions": {},
    }

    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=201)

    user = User.query.filter_by(email_address="user@digital.cabinet-office.gov.uk").first()
    assert json_resp["data"]["id"] == str(user.id)
    assert user.auth_type == SMS_AUTH_TYPE


def test_post_user_missing_attribute_email(admin_request, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute email.
    """
    User.query.delete()
    data = {
        "name": "Test User",
        "password": "password123456",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
    }
    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=400)

    assert User.query.count() == 0
    assert {"email_address": ["Missing data for required field."]} == json_resp["message"]


def test_create_user_missing_attribute_password(admin_request, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute password.
    """
    User.query.delete()
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
    }
    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=400)
    assert User.query.count() == 0
    assert {"password": ["Missing data for required field."]} == json_resp["message"]


def test_can_create_user_with_email_auth_and_no_mobile(admin_request, notify_db_session):
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password123456",
        "mobile_number": None,
        "auth_type": EMAIL_AUTH_TYPE,
    }

    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=201)

    assert json_resp["data"]["auth_type"] == EMAIL_AUTH_TYPE
    assert json_resp["data"]["mobile_number"] is None


def test_cannot_create_user_with_sms_auth_and_no_mobile(admin_request, notify_db_session):
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password123456",
        "mobile_number": None,
        "auth_type": SMS_AUTH_TYPE,
    }

    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=400)

    assert json_resp["message"] == "Mobile number must be set if auth_type is set to sms_auth"


def test_cannot_create_user_with_empty_strings(admin_request, notify_db_session):
    data = {
        "name": "",
        "email_address": "",
        "password": "password123456",
        "mobile_number": "",
        "auth_type": EMAIL_AUTH_TYPE,
    }
    resp = admin_request.post("user.create_user", _data=data, _expected_status=400)
    assert resp["message"] == {
        "email_address": ["Not a valid email address"],
        "mobile_number": ["Invalid phone number: Not enough digits"],
        "name": ["Invalid name"],
    }


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [("name", "New User"), ("email_address", "newuser@mail.com"), ("mobile_number", "+4407700900460")],
)
def test_post_user_attribute(admin_request, sample_user, user_attribute, user_value):
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {user_attribute: user_value}

    json_resp = admin_request.post("user.update_user_attribute", user_id=sample_user.id, _data=update_dict)

    assert json_resp["data"][user_attribute] == user_value
    assert getattr(sample_user, user_attribute) == user_value


@pytest.mark.parametrize(
    "user_attribute, user_value, arguments",
    [
        ("name", "New User", None),
        (
            "email_address",
            "newuser@mail.com",
            dict(
                api_key_id=None,
                key_type="normal",
                notification_type="email",
                personalisation={
                    "name": "Test User",
                    "servicemanagername": "Service Manago",
                    "email address": "newuser@mail.com",
                },
                recipient="newuser@mail.com",
                service=mock.ANY,
                template_id=uuid.UUID("c73f1d71-4049-46d5-a647-d013bdeca3f0"),
                template_version=1,
            ),
        ),
        (
            "mobile_number",
            "+4407700900460",
            dict(
                api_key_id=None,
                key_type="normal",
                notification_type="sms",
                personalisation={
                    "name": "Test User",
                    "servicemanagername": "Service Manago",
                    "email address": "notify@digital.cabinet-office.gov.uk",
                },
                recipient="+4407700900460",
                service=mock.ANY,
                template_id=uuid.UUID("8a31520f-4751-4789-8ea1-fe54496725eb"),
                template_version=1,
            ),
        ),
    ],
)
def test_post_user_attribute_with_updated_by(
    admin_request,
    mocker,
    sample_user,
    user_attribute,
    user_value,
    arguments,
):
    updater = create_user(name="Service Manago", email="notify_manago@digital.cabinet-office.gov.uk")
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {user_attribute: user_value, "updated_by": str(updater.id)}
    mocked = mocker.patch("app.user.rest.notify_send")
    json_resp = admin_request.post("user.update_user_attribute", user_id=sample_user.id, _data=update_dict)
    assert json_resp["data"][user_attribute] == user_value
    if arguments:
        mocked.assert_called_once()
    else:
        mocked.assert_not_called()


def test_archive_user(mocker, admin_request, sample_user):
    archive_mock = mocker.patch("app.user.rest.dao_archive_user")

    admin_request.post("user.archive_user", user_id=sample_user.id, _expected_status=204)

    archive_mock.assert_called_once_with(sample_user)


def test_archive_user_when_user_does_not_exist_gives_404(mocker, admin_request, fake_uuid, notify_db_session):
    archive_mock = mocker.patch("app.user.rest.dao_archive_user")

    admin_request.post("user.archive_user", user_id=fake_uuid, _expected_status=404)

    archive_mock.assert_not_called()


def test_archive_user_when_user_cannot_be_archived(mocker, admin_request, sample_user):
    mocker.patch("app.dao.users_dao.user_can_be_archived", return_value=False)

    json_resp = admin_request.post("user.archive_user", user_id=sample_user.id, _expected_status=400)
    msg = "User can’t be removed from a service - check all services have another team member with manage_settings"

    assert json_resp["message"] == msg


def test_get_user_by_email(admin_request, sample_service):
    sample_user = sample_service.users[0]

    json_resp = admin_request.get("user.get_by_email", email=sample_user.email_address)

    expected_permissions = default_service_permissions
    fetched = json_resp["data"]

    assert str(sample_user.id) == fetched["id"]
    assert sample_user.name == fetched["name"]
    assert sample_user.mobile_number == fetched["mobile_number"]
    assert sample_user.email_address == fetched["email_address"]
    assert sample_user.state == fetched["state"]
    assert sorted(expected_permissions) == sorted(fetched["permissions"][str(sample_service.id)])


def test_get_user_by_email_not_found_returns_404(admin_request, sample_user):
    json_resp = admin_request.get("user.get_by_email", email="no_user@digital.gov.uk", _expected_status=404)
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_get_user_by_email_bad_url_returns_404(admin_request, sample_user):
    json_resp = admin_request.get("user.get_by_email", _expected_status=400)
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "Invalid request. Email query string param required"


def test_fetch_user_by_email(admin_request, mocker, notify_db_session):
    user = create_user(email="foo@bar.test")

    create_user(email="foo@bar.other_email.test")
    create_user(email="other_email.foo@bar.test")

    mocker.patch("app.user.rest._pending_registration", return_value=False)
    add_failed_login_for_requester = mocker.patch("app.user.rest.add_failed_login_for_requester")

    resp = admin_request.post("user.fetch_user_by_email", _data={"email": user.email_address}, _expected_status=200)

    assert resp["data"]["id"] == str(user.id)
    assert resp["data"]["email_address"] == user.email_address
    add_failed_login_for_requester.assert_not_called()


def test_fetch_user_by_email_not_found_returns_404(admin_request, mocker, notify_db_session):
    create_user(email="foo@bar.other_email.test")

    mocker.patch("app.failed_logins.rest.add_failed_login_for_requester")

    resp = admin_request.post("user.fetch_user_by_email", _data={"email": "doesnt@exist.test"}, _expected_status=404)
    assert resp["result"] == "error"
    assert resp["message"] == "No result found"


def test_email_not_found_for_active_user_logs_failed_login(admin_request, mocker):
    create_user(email="foo@bar.other_email.test")

    mocker.patch("app.user.rest._pending_registration", return_value=False)
    add_failed_login_for_requester = mocker.patch("app.user.rest.add_failed_login_for_requester")

    resp = admin_request.post("user.fetch_user_by_email", _data={"email": "doesnt@exist.test"}, _expected_status=404)

    assert resp["result"] == "error"
    add_failed_login_for_requester.assert_called_once()


def test_email_not_found_for_registering_user_does_not_log_failed_login(admin_request, mocker):
    create_user(email="foo@bar.other_email.test")

    mocker.patch("app.user.rest._pending_registration", return_value=True)
    add_failed_login_for_requester = mocker.patch("app.user.rest.add_failed_login_for_requester")

    resp = admin_request.post("user.fetch_user_by_email", _data={"email": "doesnt@exist.test"}, _expected_status=404)

    assert resp["result"] == "error"
    add_failed_login_for_requester.assert_not_called()


def test_fetch_user_by_email_without_email_returns_400(admin_request, notify_db_session):
    resp = admin_request.post("user.fetch_user_by_email", _data={}, _expected_status=400)
    assert resp["result"] == "error"
    assert resp["message"] == {"email": ["Missing data for required field."]}


def test_get_user_with_permissions(admin_request, sample_user_service_permission):
    json_resp = admin_request.get(
        "user.get_user",
        user_id=str(sample_user_service_permission.user.id),
    )
    permissions = json_resp["data"]["permissions"]
    assert sample_user_service_permission.permission in permissions[str(sample_user_service_permission.service.id)]


def test_set_user_permissions(admin_request, sample_user, sample_service):
    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data={"permissions": [{"permission": MANAGE_SETTINGS}]},
        _expected_status=204,
    )

    permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_SETTINGS


def test_set_user_permissions_multiple(admin_request, sample_user, sample_service):
    data = {"permissions": [{"permission": MANAGE_SETTINGS}, {"permission": MANAGE_TEMPLATES}]}
    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_SETTINGS
    permission = Permission.query.filter_by(permission=MANAGE_TEMPLATES).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_TEMPLATES


def test_set_user_permissions_remove_old(admin_request, sample_user, sample_service):
    data = {"permissions": [{"permission": MANAGE_SETTINGS}]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    query = Permission.query.filter_by(user=sample_user)
    assert query.count() == 1
    assert query.first().permission == MANAGE_SETTINGS


def test_set_user_folder_permissions(admin_request, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)
    data = {"permissions": [], "folder_permissions": [str(tf1.id), str(tf2.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    assert len(service_user.folders) == 2
    assert tf1 in service_user.folders
    assert tf2 in service_user.folders


def test_set_user_folder_permissions_when_user_does_not_belong_to_service(admin_request, sample_user):
    service = create_service()
    tf1 = create_template_folder(service)
    tf2 = create_template_folder(service)

    data = {"permissions": [], "folder_permissions": [str(tf1.id), str(tf2.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(service.id),
        _data=data,
        _expected_status=404,
    )


def test_set_user_folder_permissions_does_not_affect_permissions_for_other_services(
    admin_request,
    sample_user,
    sample_service,
):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_2 = create_service(sample_user, service_name="other service")
    tf3 = create_template_folder(service_2)

    sample_service_user = dao_get_service_user(sample_user.id, sample_service.id)
    sample_service_user.folders = [tf1]
    dao_update_service_user(sample_service_user)

    service_2_user = dao_get_service_user(sample_user.id, service_2.id)
    service_2_user.folders = [tf3]
    dao_update_service_user(service_2_user)

    data = {"permissions": [], "folder_permissions": [str(tf2.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    assert sample_service_user.folders == [tf2]
    assert service_2_user.folders == [tf3]


def test_update_user_folder_permissions(admin_request, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)
    tf3 = create_template_folder(sample_service)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    data = {"permissions": [], "folder_permissions": [str(tf2.id), str(tf3.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    assert len(service_user.folders) == 2
    assert tf2 in service_user.folders
    assert tf3 in service_user.folders


def test_remove_user_folder_permissions(admin_request, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    data = {"permissions": [], "folder_permissions": []}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    assert service_user.folders == []


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_send_reset_password_link(admin_request, sample_user, mocker):
    mocked = mocker.patch("app.user.rest.notify_send")
    mocker.patch("app.user.rest._create_reset_password_url", return_value="dummy_url")
    data = {"email": sample_user.email_address}

    admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=204,
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["PASSWORD_RESET_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "user_name": "Test User",
            "url": "dummy_url",
        },
    }

    mocked.assert_called_once_with(notification)


@pytest.mark.parametrize(
    "data, expected_url",
    (
        (
            {
                "email": "notify@digital.cabinet-office.gov.uk",
            },
            (f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk/new-password/"),
        ),
        (
            {
                "email": "notify@digital.cabinet-office.gov.uk",
                "admin_base_url": "https://different.example.com",
            },
            ("https://different.example.com/new-password/"),
        ),
    ),
)
@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_use_provided_base_url(
    admin_request,
    sample_user,
    mocker,
    data,
    expected_url,
):
    mocked = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)

    admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=204,
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["PASSWORD_RESET_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "user_name": "Test User",
            "url": expected_url + fake_token,
        },
    }

    mocked.assert_called_once_with(notification)


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_reset_password_link_contains_redirect_link_if_present_in_request(
    admin_request, sample_user, mocker
):
    mocked = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)

    data = {"email": sample_user.email_address, "next": "blob"}

    admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=204,
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["PASSWORD_RESET_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "user_name": "Test User",
            "url": f"https://admin.{os.environ.get('ENVIRONMENT')}.emergency-alerts.service.gov.uk/new-password/"
            + fake_token
            + "?next=blob",
        },
    }

    mocked.assert_called_once_with(notification)


def test_send_user_reset_password_should_return_400_when_email_is_missing(admin_request, mocker):
    mocked = mocker.patch("app.user.rest.notify_send")
    data = {}

    json_resp = admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=400,
    )
    assert json_resp["message"] == {"email": ["Missing data for required field."]}
    assert mocked.call_count == 0


def test_send_user_reset_password_should_return_400_when_user_doesnot_exist(admin_request, mocker):
    mocked = mocker.patch("app.user.rest.notify_send")
    bad_email_address = "bad@email.gov.uk"
    data = {"email": bad_email_address}

    json_resp = admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=404,
    )

    assert json_resp["message"] == "No result found"
    assert mocked.call_count == 0


def test_send_user_reset_password_should_return_400_when_data_is_not_email_address(admin_request, mocker):
    mocked = mocker.patch("app.user.rest.notify_send")
    bad_email_address = "bad.email.gov.uk"
    data = {"email": bad_email_address}

    json_resp = admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=400,
    )

    assert json_resp["message"] == {"email": ["Not a valid email address"]}
    assert mocked.call_count == 0


def test_send_already_registered_email(admin_request, sample_user, mocker):
    data = {"email": sample_user.email_address}
    mocked = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)

    admin_request.post(
        "user.send_already_registered_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=204,
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["ALREADY_REGISTERED_EMAIL_TEMPLATE_ID"],
        "recipient": sample_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "signin_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/sign-in",
            "forgot_password_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/forgot-password",
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        },
    }

    mocked.assert_called_once_with(notification)


def test_send_already_registered_email_returns_400_when_data_is_missing(admin_request, sample_user):
    data = {}

    json_resp = admin_request.post(
        "user.send_already_registered_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=400,
    )
    assert json_resp["message"] == {"email": ["Missing data for required field."]}


def test_send_user_confirm_new_email_returns_204(admin_request, sample_user, mocker):
    mocked = mocker.patch("app.user.rest.notify_send")
    fake_token = "0123456789"
    mocker.patch("app.utils.generate_token", return_value=fake_token)
    new_email = "new_address@dig.gov.uk"
    data = {"email": new_email}

    admin_request.post(
        "user.send_user_confirm_new_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=204,
    )

    notification = {
        "type": "email",
        "template_id": current_app.config["CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID"],
        "recipient": new_email,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "name": "Test User",
            "url": current_app.config["ADMIN_EXTERNAL_URL"] + "/user-profile/email/confirm/" + fake_token,
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        },
    }

    mocked.assert_called_once_with(notification)


def test_send_user_confirm_new_email_returns_400_when_email_missing(admin_request, sample_user, mocker):
    mocked = mocker.patch("app.user.rest.notify_send")
    data = {}

    json_resp = admin_request.post(
        "user.send_user_confirm_new_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=400,
    )
    assert json_resp["message"] == {"email": ["Missing data for required field."]}
    mocked.assert_not_called()


@freeze_time("2020-02-14T12:00:00")
def test_update_user_password_saves_correctly(admin_request, sample_service):
    sample_user = sample_service.users[0]
    new_password = "A1234567890!?!"
    data = {"_password": "A1234567890!?!"}

    json_resp = admin_request.post("user.update_password", user_id=str(sample_user.id), _data=data)

    assert json_resp["data"]["password_changed_at"] is not None
    data = {"password": new_password}

    admin_request.post("user.verify_user_password", user_id=str(sample_user.id), _data=data, _expected_status=204)


def test_activate_user(admin_request, sample_user):
    sample_user.state = "pending"

    resp = admin_request.post("user.activate_user", user_id=sample_user.id)

    assert resp["data"]["id"] == str(sample_user.id)
    assert resp["data"]["state"] == "active"
    assert sample_user.state == "active"


def test_activate_user_fails_if_already_active(admin_request, sample_user):
    resp = admin_request.post("user.activate_user", user_id=sample_user.id, _expected_status=400)
    assert resp["message"] == "User already active"
    assert sample_user.state == "active"


def test_update_user_auth_type(admin_request, sample_user):
    assert sample_user.auth_type == "sms_auth"
    resp = admin_request.post(
        "user.update_user_attribute",
        user_id=sample_user.id,
        _data={"auth_type": "email_auth"},
    )

    assert resp["data"]["id"] == str(sample_user.id)
    assert resp["data"]["auth_type"] == "email_auth"


def test_can_set_email_auth_and_remove_mobile_at_same_time(admin_request, sample_user):
    sample_user.auth_type = SMS_AUTH_TYPE

    admin_request.post(
        "user.update_user_attribute",
        user_id=sample_user.id,
        _data={
            "mobile_number": None,
            "auth_type": EMAIL_AUTH_TYPE,
        },
    )

    assert sample_user.mobile_number is None
    assert sample_user.auth_type == EMAIL_AUTH_TYPE


def test_cannot_remove_mobile_if_sms_auth(admin_request, sample_user):
    sample_user.auth_type = SMS_AUTH_TYPE

    json_resp = admin_request.post(
        "user.update_user_attribute", user_id=sample_user.id, _data={"mobile_number": None}, _expected_status=400
    )

    assert json_resp["message"] == "Mobile number must be set if auth_type is set to sms_auth"


def test_can_remove_mobile_if_email_auth(admin_request, sample_user):
    sample_user.auth_type = EMAIL_AUTH_TYPE

    admin_request.post(
        "user.update_user_attribute",
        user_id=sample_user.id,
        _data={"mobile_number": None},
    )

    assert sample_user.mobile_number is None


def test_cannot_update_user_with_mobile_number_as_empty_string(admin_request, sample_user):
    sample_user.auth_type = EMAIL_AUTH_TYPE

    resp = admin_request.post(
        "user.update_user_attribute", user_id=sample_user.id, _data={"mobile_number": ""}, _expected_status=400
    )
    assert resp["message"]["mobile_number"] == ["Invalid phone number: Not enough digits"]


def test_cannot_update_user_password_using_attributes_method(admin_request, sample_user):
    resp = admin_request.post(
        "user.update_user_attribute", user_id=sample_user.id, _data={"password": "foo"}, _expected_status=400
    )
    assert resp == {"message": {"_schema": ["Unknown field name password"]}, "result": "error"}


def test_get_orgs_and_services_nests_services(admin_request, sample_user):
    org1 = create_organisation(name="org1")
    org2 = create_organisation(name="org2")
    service1 = create_service(service_name="service1")
    service2 = create_service(service_name="service2")
    service3 = create_service(service_name="service3")

    org1.services = [service1, service2]
    org2.services = []

    sample_user.organisations = [org1, org2]
    sample_user.services = [service1, service2, service3]

    resp = admin_request.get("user.get_organisations_and_services_for_user", user_id=sample_user.id)

    assert set(resp.keys()) == {
        "organisations",
        "services",
    }
    assert resp["organisations"] == [
        {
            "name": org1.name,
            "id": str(org1.id),
            "count_of_live_services": 2,
        },
        {
            "name": org2.name,
            "id": str(org2.id),
            "count_of_live_services": 0,
        },
    ]
    assert resp["services"] == [
        {
            "name": service1.name,
            "id": str(service1.id),
            "restricted": False,
            "organisation": str(org1.id),
        },
        {
            "name": service2.name,
            "id": str(service2.id),
            "restricted": False,
            "organisation": str(org1.id),
        },
        {
            "name": service3.name,
            "id": str(service3.id),
            "restricted": False,
            "organisation": None,
        },
    ]


def test_get_orgs_and_services_only_returns_active(admin_request, sample_user):
    org1 = create_organisation(name="org1", active=True)
    org2 = create_organisation(name="org2", active=False)

    # in an active org
    service1 = create_service(service_name="service1", active=True)
    service2 = create_service(service_name="service2", active=False)
    # active but in an inactive org
    service3 = create_service(service_name="service3", active=True)
    # not in an org
    service4 = create_service(service_name="service4", active=True)
    service5 = create_service(service_name="service5", active=False)

    org1.services = [service1, service2]
    org2.services = [service3]

    sample_user.organisations = [org1, org2]
    sample_user.services = [service1, service2, service3, service4, service5]

    resp = admin_request.get("user.get_organisations_and_services_for_user", user_id=sample_user.id)

    assert set(resp.keys()) == {
        "organisations",
        "services",
    }
    assert resp["organisations"] == [
        {
            "name": org1.name,
            "id": str(org1.id),
            "count_of_live_services": 1,
        }
    ]
    assert resp["services"] == [
        {"name": service1.name, "id": str(service1.id), "restricted": False, "organisation": str(org1.id)},
        {"name": service3.name, "id": str(service3.id), "restricted": False, "organisation": str(org2.id)},
        {
            "name": service4.name,
            "id": str(service4.id),
            "restricted": False,
            "organisation": None,
        },
    ]


def test_get_orgs_and_services_only_shows_users_orgs_and_services(admin_request, sample_user):
    other_user = create_user(email="other@user.com")

    org1 = create_organisation(name="org1")
    org2 = create_organisation(name="org2")
    service1 = create_service(service_name="service1")
    service2 = create_service(service_name="service2")

    org1.services = [service1]

    sample_user.organisations = [org2]
    sample_user.services = [service1]

    other_user.organisations = [org1, org2]
    other_user.services = [service1, service2]

    resp = admin_request.get("user.get_organisations_and_services_for_user", user_id=sample_user.id)

    assert set(resp.keys()) == {
        "organisations",
        "services",
    }
    assert resp["organisations"] == [
        {
            "name": org2.name,
            "id": str(org2.id),
            "count_of_live_services": 0,
        }
    ]
    # 'services' always returns the org_id no matter whether the user
    # belongs to that org or not
    assert resp["services"] == [
        {
            "name": service1.name,
            "id": str(service1.id),
            "restricted": False,
            "organisation": str(org1.id),
        }
    ]


def test_find_users_by_email_finds_user_by_partial_email(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    create_user(email="me.ignorra@foo.com")
    data = {"email": "findel"}

    users = admin_request.post(
        "user.find_users_by_email",
        _data=data,
    )

    assert len(users["data"]) == 1
    assert users["data"][0]["email_address"] == "findel.mestro@foo.com"


def test_find_users_by_email_finds_user_by_full_email(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    create_user(email="me.ignorra@foo.com")
    data = {"email": "findel.mestro@foo.com"}

    users = admin_request.post(
        "user.find_users_by_email",
        _data=data,
    )

    assert len(users["data"]) == 1
    assert users["data"][0]["email_address"] == "findel.mestro@foo.com"


def test_find_users_by_email_handles_no_results(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    create_user(email="me.ignorra@foo.com")
    data = {"email": "rogue"}

    users = admin_request.post(
        "user.find_users_by_email",
        _data=data,
    )

    assert users["data"] == []


def test_search_for_users_by_email_handles_incorrect_data_format(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    data = {"email": 1}

    json = admin_request.post("user.find_users_by_email", _data=data, _expected_status=400)

    assert json["message"] == {"email": ["Not a valid string."]}


@freeze_time("2020-01-01 11:00")
def test_complete_login_after_webauthn_authentication_attempt_resets_login_if_successful(admin_request, sample_user):
    sample_user.failed_login_count = 1

    assert sample_user.current_session_id is None
    assert sample_user.logged_in_at is None

    webauthn_credential = create_webauthn_credential(sample_user)
    assert webauthn_credential.logged_in_at is None

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": True},
        _expected_status=204,
    )

    assert sample_user.current_session_id is not None
    assert sample_user.failed_login_count == 0
    assert sample_user.logged_in_at == datetime(2020, 1, 1, 11, 0)
    assert webauthn_credential.logged_in_at is None


@freeze_time("2020-01-01 11:00")
def test_complete_login_after_webauthn_authentication_attempt_updates_logged_in_at_for_supplied_webauthn_credential(
    admin_request, sample_user
):
    assert sample_user.current_session_id is None
    assert sample_user.logged_in_at is None

    webauthn_credential = create_webauthn_credential(sample_user)
    assert webauthn_credential.logged_in_at is None

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": True, "webauthn_credential_id": str(webauthn_credential.id)},
        _expected_status=204,
    )

    assert sample_user.logged_in_at == datetime(2020, 1, 1, 11, 0)
    assert webauthn_credential.logged_in_at == datetime(2020, 1, 1, 11, 0)


def test_complete_login_after_webauthn_authentication_attempt_returns_204_when_not_successful(
    admin_request, sample_user
):
    # when unsuccessful this endpoint is used to bump the failed count. the endpoint still worked
    # properly so should return 204 (no content).
    sample_user.failed_login_count = 1

    assert sample_user.current_session_id is None
    assert sample_user.logged_in_at is None

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": False},
        _expected_status=204,
    )

    assert sample_user.current_session_id is None
    assert sample_user.failed_login_count == 2
    assert sample_user.logged_in_at is None


def test_complete_login_after_webauthn_authentication_attempt_raises_403_if_max_login_count_exceeded(
    admin_request, sample_user
):
    # when unsuccessful this endpoint is used to bump the failed count. the endpoint still worked
    # properly so should return 204 (no content).
    sample_user.failed_login_count = 10

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": True},
        _expected_status=403,
    )

    assert sample_user.current_session_id is None
    assert sample_user.failed_login_count == 10
    assert sample_user.logged_in_at is None


def test_complete_login_after_webauthn_authentication_attempt_raises_400_if_schema_invalid(admin_request):
    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=uuid.uuid4(),
        _data={"successful": "True"},
        _expected_status=400,
    )


def test_check_password_is_valid_rejects_reused_password(admin_request, sample_service):
    data = {"_password": "1234567890TEST!!!"}
    new_data = {"_password": "1234567890TEST!!!!"}
    sample_user = sample_service.users[0]

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=data, _expected_status=200)
    assert json_resp["data"]["password_changed_at"] is not None

    json_resp = admin_request.post(
        "user.check_password_is_valid", user_id=sample_user.id, _data=new_data, _expected_status=200
    )

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=new_data, _expected_status=200)

    assert json_resp["data"]["password_changed_at"] is not None

    json_resp = admin_request.post(
        "user.check_password_is_valid", user_id=sample_user.id, _data=data, _expected_status=400
    )
    assert json_resp["errors"] == ["You've used this password before. Please choose a new one."]


def test_check_password_is_valid_low_entropy_password(admin_request, sample_service):
    new_password = "low entropy"
    data = {"_password": new_password}
    sample_user = sample_service.users[0]

    json_resp = admin_request.post(
        "user.check_password_is_valid", user_id=sample_user.id, _data=data, _expected_status=400
    )

    assert json_resp["errors"] == ["Your password is not strong enough, try adding more words"]


def test_check_password_is_valid_rejects_common_password(admin_request, sample_service, notify_db_session):
    new_password = "common password 123"
    data = {"_password": new_password}
    sample_user = sample_service.users[0]

    common_password = CommonPasswords(password=new_password)
    notify_db_session.add(common_password)
    notify_db_session.commit()

    json_resp = admin_request.post(
        "user.check_password_is_valid", user_id=sample_user.id, _data=data, _expected_status=400
    )

    assert json_resp["errors"] == ["Your password is too common. Please choose a new one."]


def test_update_password_rejects_reused_password(admin_request, sample_service):
    data = {"_password": "1234567890TEST!!!"}
    new_data = {"_password": "1234567890TEST!!!!"}
    sample_user = sample_service.users[0]

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=data, _expected_status=200)
    assert json_resp["data"]["password_changed_at"] is not None

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=new_data, _expected_status=200)

    assert json_resp["data"]["password_changed_at"] is not None

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=data, _expected_status=400)
    assert json_resp["errors"] == ["You've used this password before. Please choose a new one."]


def test_update_password_rejects_low_entropy_password(admin_request, sample_service):
    new_password = "low entropy"
    data = {"_password": new_password}
    sample_user = sample_service.users[0]

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=data, _expected_status=400)

    assert json_resp["errors"] == ["Your password is not strong enough, try adding more words"]


def test_update_user_password_rejects_common_password(admin_request, sample_service, notify_db_session):
    new_password = "common password 123"
    data = {"_password": new_password}
    sample_user = sample_service.users[0]

    common_password = CommonPasswords(password=new_password)
    notify_db_session.add(common_password)
    notify_db_session.commit()

    json_resp = admin_request.post("user.update_password", user_id=sample_user.id, _data=data, _expected_status=400)

    assert json_resp["errors"] == ["Your password is too common. Please choose a new one."]


@pytest.mark.parametrize(
    "email, to_be_created, return_value",
    [("test@digital.cabinet-office.gov.uk", False, False), ("findel.mestro@foo.com", True, True)],
)
def test_check_email_already_in_use(admin_request, email, to_be_created, return_value):
    if to_be_created:
        create_user(email=email)
    data = {"email": email}
    json_resp = admin_request.post("user.check_email_already_in_use", _data=data, _expected_status=200)
    assert json_resp is return_value
