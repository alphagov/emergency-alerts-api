import json
import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytz
import requests_mock
from flask import current_app, url_for

from app import db
from app.dao.api_key_dao import save_model_api_key
from app.dao.broadcast_service_dao import (
    insert_or_update_service_broadcast_settings,
)
from app.dao.invited_user_dao import save_invited_user
from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_create_organisation,
)
from app.dao.services_dao import dao_add_user_to_service, dao_create_service
from app.dao.templates_dao import dao_create_template
from app.dao.users_dao import create_secret_code, create_user_code
from app.history_meta import create_history
from app.models import (
    BROADCAST_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    SERVICE_PERMISSION_TYPES,
    ApiKey,
    InvitedUser,
    Organisation,
    Permission,
    Service,
    Template,
    TemplateHistory,
)
from tests import (
    create_admin_authorization_header,
    create_service_authorization_header,
)
from tests.app.db import (
    create_api_key,
    create_invited_org_user,
    create_service,
    create_template,
    create_user,
)

os.environ["AWS_DEFAULT_REGION"] = "eu-west-2"
test_ip_1 = "192.0.2.15"
test_ip_2 = "192.0.2.30"
test_ip_3 = "127.0.0.1"


@pytest.yield_fixture
def rmock():
    with requests_mock.mock() as rmock:
        yield rmock


@pytest.fixture(scope="function")
def service_factory(sample_user):
    class ServiceFactory(object):
        def get(self, service_name, user=None, template_type=None):
            if not user:
                user = sample_user

            service = create_service(
                service_name=service_name,
                service_permissions=None,
                user=user,
                check_if_service_exists=True,
            )
            return service

    return ServiceFactory()


@pytest.fixture(scope="function")
def sample_user(notify_db_session):
    return create_user(email="notify@digital.cabinet-office.gov.uk")


@pytest.fixture(scope="function")
def notify_user(notify_db_session):
    return create_user(
        email="notify-service-user@digital.cabinet-office.gov.uk", id_=current_app.config["NOTIFY_USER_ID"]
    )


def create_code(notify_db_session, code_type):
    code = create_secret_code()
    usr = create_user()
    return create_user_code(usr, code, code_type), code


@pytest.fixture(scope="function")
def sample_sms_code(notify_db_session):
    code, txt_code = create_code(notify_db_session, code_type="sms")
    code.txt_code = txt_code
    return code


@pytest.fixture(scope="function")
def sample_service(sample_user):
    service_name = "Sample service"

    data = {
        "name": service_name,
        "restricted": False,
        "created_by": sample_user,
        "crown": True,
    }
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = Service(**data)
        dao_create_service(service, sample_user, service_permissions=None)
    else:
        if sample_user not in service.users:
            dao_add_user_to_service(service, sample_user)

    return service


@pytest.fixture(scope="function")
def sample_broadcast_service(broadcast_organisation, sample_user):
    service_name = "Sample broadcast service"

    data = {
        "name": service_name,
        "restricted": False,
        "created_by": sample_user,
        "crown": True,
    }
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = Service(**data)
        dao_create_service(service, sample_user, service_permissions=[BROADCAST_TYPE])
        insert_or_update_service_broadcast_settings(service, channel="severe")
        dao_add_service_to_organisation(service, current_app.config["BROADCAST_ORGANISATION_ID"])
    else:
        if sample_user not in service.users:
            dao_add_user_to_service(service, sample_user)

    return service


@pytest.fixture(scope="function")
def sample_broadcast_service_2(broadcast_organisation, sample_user):
    service_name = "Sample broadcast service 2"

    data = {
        "name": service_name,
        "restricted": False,
        "created_by": sample_user,
        "crown": True,
    }
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = Service(**data)
        dao_create_service(service, sample_user, service_permissions=[BROADCAST_TYPE])
        insert_or_update_service_broadcast_settings(service, channel="severe")
        dao_add_service_to_organisation(service, current_app.config["BROADCAST_ORGANISATION_ID"])
    else:
        if sample_user not in service.users:
            dao_add_user_to_service(service, sample_user)

    return service


@pytest.fixture(scope="function", name="sample_service_full_permissions")
def _sample_service_full_permissions(notify_db_session):
    service = create_service(
        service_name="sample service full permissions",
        service_permissions=set(SERVICE_PERMISSION_TYPES),
        check_if_service_exists=True,
    )
    return service


@pytest.fixture(scope="function")
def sample_template(sample_user):
    # This will be the same service as the one returned by the sample_service fixture as we look for a
    # service with the same name - "Sample service" - before creating a new one.
    service = create_service(service_permissions=[BROADCAST_TYPE], check_if_service_exists=True)

    data = {
        "name": "Template Name",
        "template_type": BROADCAST_TYPE,
        "content": "This is a template:\nwith a newline",
        "service": service,
        "created_by": sample_user,
        "archived": False,
    }
    template = Template(**data)
    dao_create_template(template)

    return template


# @pytest.fixture(scope="function")
# def sample_template_without_sms_permission(notify_db_session):
#     service = create_service(service_permissions=[EMAIL_TYPE], check_if_service_exists=True)
#     return create_template(service, template_type=SMS_TYPE)


@pytest.fixture(scope="function")
def sample_template_with_placeholders(sample_service):
    # deliberate space and title case in placeholder
    return create_template(sample_service, content="Hello (( Name))\nYour thing is due soon")


# @pytest.fixture(scope="function")
# def sample_template_without_email_permission(notify_db_session):
#     service = create_service(service_permissions=[SMS_TYPE], check_if_service_exists=True)
#     return create_template(service, template_type=EMAIL_TYPE)


@pytest.fixture(scope="function")
def sample_api_key(notify_db_session):
    service = create_service(check_if_service_exists=True)
    data = {"service": service, "name": uuid.uuid4(), "created_by": service.created_by, "key_type": KEY_TYPE_NORMAL}
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    return api_key


@pytest.fixture(scope="function")
def sample_test_api_key(sample_api_key):
    service = create_service(check_if_service_exists=True)

    return create_api_key(service, key_type=KEY_TYPE_TEST)


@pytest.fixture(scope="function")
def sample_team_api_key(sample_api_key):
    service = create_service(check_if_service_exists=True)

    return create_api_key(service, key_type=KEY_TYPE_TEAM)


@pytest.fixture(scope="function")
def sample_invited_user(notify_db_session):
    service = create_service(check_if_service_exists=True)
    to_email_address = "invited_user@digital.gov.uk"

    from_user = service.users[0]

    data = {
        "service": service,
        "email_address": to_email_address,
        "from_user": from_user,
        "permissions": "create_broadcasts,manage_service,manage_api_keys",
        "folder_permissions": ["folder_1_id", "folder_2_id"],
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)
    return invited_user


@pytest.fixture(scope="function")
def sample_invited_org_user(sample_user, sample_organisation):
    return create_invited_org_user(sample_organisation, sample_user)


@pytest.fixture(scope="function")
def sample_user_service_permission(sample_user):
    service = create_service(user=sample_user, check_if_service_exists=True)
    permission = "manage_settings"

    data = {"user": sample_user, "service": service, "permission": permission}
    p_model = Permission.query.filter_by(user=sample_user, service=service, permission=permission).first()
    if not p_model:
        p_model = Permission(**data)
        db.session.add(p_model)
        db.session.commit()
    return p_model


@pytest.fixture(scope="function")
def fake_uuid():
    return "6ce466d0-fd6a-11e5-82f5-e0accb9d11a6"


@pytest.fixture(scope="function")
def sms_code_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="SMS_CODE_TEMPLATE_ID",
        content="((verify_code))",
        template_type="sms",
    )


@pytest.fixture(scope="function")
def email_2fa_code_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="EMAIL_2FA_TEMPLATE_ID",
        content=("Hi ((name))," "" "To sign in to GOV.​UK Notify please open this link:" "((url))"),
        subject="Sign in to GOV.UK Notify",
        template_type="email",
    )


@pytest.fixture(scope="function")
def email_verification_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID",
        content="((user_name)) use ((url)) to complete registration",
        template_type="email",
    )


@pytest.fixture(scope="function")
def invitation_email_template(notify_service):
    content = ("((user_name)) is invited to Notify by ((service_name)) ((url)) to complete registration",)
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="INVITATION_EMAIL_TEMPLATE_ID",
        content=content,
        subject="Invitation to ((service_name))",
        template_type="email",
    )


@pytest.fixture(scope="function")
def broadcast_invitation_email_template(notify_service):
    content = ("((user_name)) is invited to broadcast Notify by ((service_name)) ((url)) to complete registration",)
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="BROADCAST_INVITATION_EMAIL_TEMPLATE_ID",
        content=content,
        subject="Invitation to ((service_name))",
        template_type="email",
    )


@pytest.fixture(scope="function")
def org_invite_email_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID",
        content="((user_name)) ((organisation_name)) ((url))",
        subject="Invitation to ((organisation_name))",
        template_type="email",
    )


@pytest.fixture(scope="function")
def password_reset_email_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="PASSWORD_RESET_TEMPLATE_ID",
        content="((user_name)) you can reset password by clicking ((url))",
        subject="Reset your password",
        template_type="email",
    )


@pytest.fixture(scope="function")
def team_member_email_edit_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID",
        content="Hi ((name)) ((servicemanagername)) changed your email to ((email address))",
        subject="Your GOV.UK Notify email address has changed",
        template_type="email",
    )


@pytest.fixture(scope="function")
def team_member_mobile_edit_template(notify_service):
    return create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID",
        content="Your mobile number was changed by ((servicemanagername)).",
        template_type="sms",
    )


@pytest.fixture(scope="function")
def change_email_confirmation_template(notify_service):
    content = """Hi ((name)),
              Click this link to confirm your new email address:
              ((url))
              If you didn’t try to change the email address for your GOV.UK Notify account, let us know here:
              ((feedback_url))"""
    template = create_custom_template(
        service=notify_service,
        user=notify_service.users[0],
        template_config_name="CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID",
        content=content,
        template_type="email",
    )
    return template


def create_custom_template(service, user, template_config_name, template_type, content="", subject=None):
    template = Template.query.get(current_app.config[template_config_name])
    if not template:
        data = {
            "id": current_app.config[template_config_name],
            "name": template_config_name,
            "template_type": template_type,
            "content": content,
            "service": service,
            "created_by": user,
            "subject": subject,
            "archived": False,
        }
        template = Template(**data)
        db.session.add(template)
        db.session.add(create_history(template, TemplateHistory))
        db.session.commit()
    return template


@pytest.fixture
def notify_service(notify_db_session, sample_user):
    service = Service.query.get(current_app.config["NOTIFY_SERVICE_ID"])
    if not service:
        service = Service(
            name="Notify Service",
            restricted=False,
            created_by=sample_user,
        )
        dao_create_service(service=service, service_id=current_app.config["NOTIFY_SERVICE_ID"], user=sample_user)
    return service


@pytest.fixture
def sample_organisation(notify_db_session):
    org = Organisation(name="sample organisation")
    dao_create_organisation(org)
    return org


@pytest.fixture
def broadcast_organisation(notify_db_session):
    org = Organisation.query.get(current_app.config["BROADCAST_ORGANISATION_ID"])
    if not org:
        org = Organisation(id=current_app.config["BROADCAST_ORGANISATION_ID"], name="broadcast organisation")
        dao_create_organisation(org)

    return org


@pytest.fixture
def admin_request(client):
    class AdminRequest:
        app = client.application

        @staticmethod
        def get(endpoint, _expected_status=200, **endpoint_kwargs):
            resp = client.get(
                url_for(endpoint, **(endpoint_kwargs or {})), headers=[create_admin_authorization_header()]
            )
            json_resp = resp.json
            assert resp.status_code == _expected_status
            return json_resp

        @staticmethod
        def post(endpoint, _data=None, _expected_status=200, **endpoint_kwargs):
            resp = client.post(
                url_for(endpoint, **(endpoint_kwargs or {})),
                data=json.dumps(_data),
                headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
            )
            if resp.get_data():
                json_resp = resp.json
            else:
                json_resp = None
            assert resp.status_code == _expected_status
            return json_resp

        @staticmethod
        def delete(endpoint, _expected_status=204, **endpoint_kwargs):
            resp = client.delete(
                url_for(endpoint, **(endpoint_kwargs or {})), headers=[create_admin_authorization_header()]
            )
            if resp.get_data():
                json_resp = resp.json
            else:
                json_resp = None
            assert resp.status_code == _expected_status, json_resp
            return json_resp

    return AdminRequest


@pytest.fixture
def api_client_request(client, notify_user):
    """
    For v2 endpoints. Same as admin_request, except all functions take a required service_id and an optional
    _api_key_type field.
    """

    # save us having to convert UUIDs to strings in test data
    def uuid_convert(o):
        if isinstance(o, uuid.UUID):
            return str(o)
        return json.JSONEncoder().default(o)

    class ApiClientRequest:
        app = client.application

        @staticmethod
        def get(service_id, endpoint, _api_key_type="normal", _expected_status=200, **endpoint_kwargs):
            resp = client.get(
                url_for(endpoint, **(endpoint_kwargs or {})),
                headers=[create_service_authorization_header(service_id, _api_key_type)],
            )
            json_resp = resp.json
            assert resp.status_code == _expected_status
            assert resp.headers["Content-type"] == "application/json"
            return json_resp

        @staticmethod
        def post(service_id, endpoint, _api_key_type="normal", _data=None, _expected_status=201, **endpoint_kwargs):
            # note that _expected_status is 201 since this endpoint is primarily used for create endpoints
            resp = client.post(
                url_for(endpoint, **(endpoint_kwargs or {})),
                data=json.dumps(_data, default=uuid_convert),
                headers=[
                    ("Content-Type", "application/json"),
                    create_service_authorization_header(service_id, _api_key_type),
                ],
            )
            if resp.get_data():
                json_resp = resp.json
                assert resp.headers["Content-type"] == "application/json"
            else:
                json_resp = None
            assert resp.status_code == _expected_status
            return json_resp

    return ApiClientRequest


def datetime_in_past(days=0, seconds=0):
    return datetime.now(tz=pytz.utc) - timedelta(days=days, seconds=seconds)
