import json
import uuid
from datetime import datetime, timedelta

import pytest
from flask import current_app, url_for
from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError

from app.dao.organisation_dao import dao_add_service_to_organisation
from app.dao.service_user_dao import dao_get_service_user
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_remove_user_from_service,
)
from app.dao.users_dao import save_model_user
from app.models import (
    BROADCAST_TYPE,
    EMAIL_AUTH_TYPE,
    EMAIL_TYPE,
    INBOUND_SMS_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    LETTER_TYPE,
    SERVICE_PERMISSION_TYPES,
    SMS_TYPE,
    UPLOAD_LETTERS,
    AnnualBilling,
    Permission,
    Service,
    ServiceBroadcastSettings,
    ServiceEmailReplyTo,
    ServiceLetterContact,
    ServicePermission,
    User,
)
from tests import create_admin_authorization_header
from tests.app.db import (
    create_api_key,
    create_domain,
    create_letter_contact,
    create_organisation,
    create_reply_to_email,
    create_service,
    create_template,
    create_template_folder,
    create_user,
)


def test_get_service_list(client, service_factory):
    service_factory.get("one")
    service_factory.get("two")
    service_factory.get("three")
    auth_header = create_admin_authorization_header()
    response = client.get("/service", headers=[auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp["data"]) == 3
    assert json_resp["data"][0]["name"] == "one"
    assert json_resp["data"][1]["name"] == "two"
    assert json_resp["data"][2]["name"] == "three"


def test_get_service_list_with_only_active_flag(client, service_factory):
    inactive = service_factory.get("one")
    active = service_factory.get("two")

    inactive.active = False

    auth_header = create_admin_authorization_header()
    response = client.get("/service?only_active=True", headers=[auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp["data"]) == 1
    assert json_resp["data"][0]["id"] == str(active.id)


def test_get_service_list_with_user_id_and_only_active_flag(admin_request, sample_user, service_factory):
    other_user = create_user(email="foo@bar.gov.uk")

    inactive = service_factory.get("one", user=sample_user)
    active = service_factory.get("two", user=sample_user)
    # from other user
    service_factory.get("three", user=other_user)

    inactive.active = False

    json_resp = admin_request.get("service.get_services", user_id=sample_user.id, only_active=True)
    assert len(json_resp["data"]) == 1
    assert json_resp["data"][0]["id"] == str(active.id)


def test_get_service_list_by_user(admin_request, sample_user, service_factory):
    other_user = create_user(email="foo@bar.gov.uk")
    service_factory.get("one", sample_user)
    service_factory.get("two", sample_user)
    service_factory.get("three", other_user)

    json_resp = admin_request.get("service.get_services", user_id=sample_user.id)
    assert len(json_resp["data"]) == 2
    assert json_resp["data"][0]["name"] == "one"
    assert json_resp["data"][1]["name"] == "two"


def test_get_service_list_by_user_should_return_empty_list_if_no_services(admin_request, sample_service):
    # service is already created by sample user
    new_user = create_user(email="foo@bar.gov.uk")

    json_resp = admin_request.get("service.get_services", user_id=new_user.id)
    assert json_resp["data"] == []


def test_get_service_list_should_return_empty_list_if_no_services(admin_request):
    json_resp = admin_request.get("service.get_services")
    assert len(json_resp["data"]) == 0


def test_find_services_by_name_finds_services(notify_db_session, admin_request, mocker):
    service_1 = create_service(service_name="ABCDEF")
    service_2 = create_service(service_name="ABCGHT")
    mock_get_services_by_partial_name = mocker.patch(
        "app.service.rest.get_services_by_partial_name", return_value=[service_1, service_2]
    )
    response = admin_request.get("service.find_services_by_name", service_name="ABC")["data"]
    mock_get_services_by_partial_name.assert_called_once_with("ABC")
    assert len(response) == 2


def test_find_services_by_name_handles_no_results(notify_db_session, admin_request, mocker):
    mock_get_services_by_partial_name = mocker.patch("app.service.rest.get_services_by_partial_name", return_value=[])
    response = admin_request.get("service.find_services_by_name", service_name="ABC")["data"]
    mock_get_services_by_partial_name.assert_called_once_with("ABC")
    assert len(response) == 0


def test_find_services_by_name_handles_no_service_name(notify_db_session, admin_request, mocker):
    mock_get_services_by_partial_name = mocker.patch("app.service.rest.get_services_by_partial_name")
    admin_request.get("service.find_services_by_name", _expected_status=400)
    mock_get_services_by_partial_name.assert_not_called()


def test_get_service_by_id(admin_request, sample_service):
    json_resp = admin_request.get("service.get_service_by_id", service_id=sample_service.id)
    assert json_resp["data"]["name"] == sample_service.name
    assert json_resp["data"]["id"] == str(sample_service.id)
    assert not json_resp["data"]["research_mode"]
    assert json_resp["data"]["prefix_sms"] is True
    assert json_resp["data"]["allowed_broadcast_provider"] is None
    assert json_resp["data"]["broadcast_channel"] is None

    assert set(json_resp["data"].keys()) == {
        "active",
        "allowed_broadcast_provider",
        "billing_contact_email_addresses",
        "billing_contact_names",
        "billing_reference",
        "broadcast_channel",
        "consent_to_research",
        "contact_link",
        "count_as_live",
        "created_at",
        "created_by",
        "email_from",
        "go_live_at",
        "go_live_user",
        "id",
        "inbound_api",
        "message_limit",
        "name",
        "notes",
        "organisation",
        "organisation_type",
        "permissions",
        "prefix_sms",
        "purchase_order_number",
        "rate_limit",
        "research_mode",
        "restricted",
        "service_callback_api",
        "volume_email",
        "volume_letter",
        "volume_sms",
    }


@pytest.mark.parametrize(
    "broadcast_channel,allowed_broadcast_provider",
    (
        ("operator", "all"),
        ("test", "all"),
        ("severe", "all"),
        ("government", "all"),
        ("operator", "o2"),
        ("test", "ee"),
        ("severe", "three"),
        ("government", "vodafone"),
    ),
)
def test_get_service_by_id_for_broadcast_service_returns_broadcast_keys(
    notify_db_session, admin_request, sample_broadcast_service, broadcast_channel, allowed_broadcast_provider
):
    sample_broadcast_service.broadcast_channel = broadcast_channel
    sample_broadcast_service.allowed_broadcast_provider = allowed_broadcast_provider

    json_resp = admin_request.get("service.get_service_by_id", service_id=sample_broadcast_service.id)
    assert json_resp["data"]["id"] == str(sample_broadcast_service.id)
    assert json_resp["data"]["allowed_broadcast_provider"] == allowed_broadcast_provider
    assert json_resp["data"]["broadcast_channel"] == broadcast_channel


@pytest.mark.parametrize("detailed", [True, False])
def test_get_service_by_id_returns_organisation_type(admin_request, sample_service, detailed):
    json_resp = admin_request.get("service.get_service_by_id", service_id=sample_service.id, detailed=detailed)
    assert json_resp["data"]["organisation_type"] is None


def test_get_service_list_has_default_permissions(admin_request, service_factory):
    service_factory.get("one")
    service_factory.get("one")
    service_factory.get("two")
    service_factory.get("three")

    json_resp = admin_request.get("service.get_services")
    assert len(json_resp["data"]) == 3
    assert all(
        set(json["permissions"])
        == {
            BROADCAST_TYPE,
            EMAIL_TYPE,
            SMS_TYPE,
            INTERNATIONAL_SMS_TYPE,
            LETTER_TYPE,
            UPLOAD_LETTERS,
            INTERNATIONAL_LETTERS,
        }
        for json in json_resp["data"]
    )


def test_get_service_by_id_has_default_service_permissions(admin_request, sample_service):
    json_resp = admin_request.get("service.get_service_by_id", service_id=sample_service.id)

    assert set(json_resp["data"]["permissions"]) == {
        BROADCAST_TYPE,
        EMAIL_TYPE,
        SMS_TYPE,
        INTERNATIONAL_SMS_TYPE,
        LETTER_TYPE,
        UPLOAD_LETTERS,
        INTERNATIONAL_LETTERS,
    }


def test_get_service_by_id_should_404_if_no_service(admin_request, notify_db_session):
    json_resp = admin_request.get("service.get_service_by_id", service_id=uuid.uuid4(), _expected_status=404)

    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_get_service_by_id_and_user(client, sample_service, sample_user):
    sample_service.reply_to_email = "something@service.com"
    create_reply_to_email(service=sample_service, email_address="new@service.com")
    auth_header = create_admin_authorization_header()
    resp = client.get("/service/{}?user_id={}".format(sample_service.id, sample_user.id), headers=[auth_header])
    assert resp.status_code == 200
    json_resp = resp.json
    assert json_resp["data"]["name"] == sample_service.name
    assert json_resp["data"]["id"] == str(sample_service.id)


def test_get_service_by_id_should_404_if_no_service_for_user(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_admin_authorization_header()
            resp = client.get("/service/{}?user_id={}".format(service_id, sample_user.id), headers=[auth_header])
            assert resp.status_code == 404
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert json_resp["message"] == "No result found"


def test_get_service_by_id_returns_go_live_user_and_go_live_at(admin_request, sample_user):
    now = datetime.utcnow()
    service = create_service(user=sample_user, go_live_user=sample_user, go_live_at=now)
    json_resp = admin_request.get("service.get_service_by_id", service_id=service.id)
    assert json_resp["data"]["go_live_user"] == str(sample_user.id)
    assert json_resp["data"]["go_live_at"] == str(now)


@pytest.mark.parametrize(
    "platform_admin, expected_count_as_live",
    (
        (True, False),
        (False, True),
    ),
)
def test_create_service(
    admin_request,
    sample_user,
    platform_admin,
    expected_count_as_live,
):
    sample_user.platform_admin = platform_admin
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
    }

    json_resp = admin_request.post("service.create_service", _data=data, _expected_status=201)

    assert json_resp["data"]["id"]
    assert json_resp["data"]["name"] == "created service"
    assert json_resp["data"]["email_from"] == "created.service"
    assert not json_resp["data"]["research_mode"]
    assert json_resp["data"]["count_as_live"] is expected_count_as_live

    service_db = Service.query.get(json_resp["data"]["id"])
    assert service_db.name == "created service"

    json_resp = admin_request.get(
        "service.get_service_by_id", service_id=json_resp["data"]["id"], user_id=sample_user.id
    )

    assert json_resp["data"]["name"] == "created service"
    assert not json_resp["data"]["research_mode"]


@pytest.mark.parametrize(
    "domain, expected_org",
    (
        (None, False),
        ("", False),
        ("unknown.gov.uk", False),
        ("unknown-example.gov.uk", False),
        ("example.gov.uk", True),
        ("test.gov.uk", True),
        ("test.example.gov.uk", True),
    ),
)
def test_create_service_with_domain_sets_organisation(
    admin_request,
    sample_user,
    domain,
    expected_org,
):
    red_herring_org = create_organisation(name="Sub example")
    create_domain("specific.example.gov.uk", red_herring_org.id)
    create_domain("aaaaaaaa.example.gov.uk", red_herring_org.id)

    org = create_organisation()
    create_domain("example.gov.uk", org.id)
    create_domain("test.gov.uk", org.id)

    another_org = create_organisation(name="Another")
    create_domain("cabinet-office.gov.uk", another_org.id)
    create_domain("cabinetoffice.gov.uk", another_org.id)

    sample_user.email_address = "test@{}".format(domain)

    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
        "service_domain": domain,
    }

    json_resp = admin_request.post("service.create_service", _data=data, _expected_status=201)

    if expected_org:
        assert json_resp["data"]["organisation"] == str(org.id)
    else:
        assert json_resp["data"]["organisation"] is None


def test_create_service_should_create_annual_billing_for_service(admin_request, sample_user):
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
    }
    assert len(AnnualBilling.query.all()) == 0
    admin_request.post("service.create_service", _data=data, _expected_status=201)

    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1


def test_create_service_should_raise_exception_and_not_create_service_if_annual_billing_query_fails(
    admin_request, sample_user, mocker
):
    mocker.patch("app.service.rest.set_default_free_allowance_for_service", side_effect=SQLAlchemyError)
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
    }
    assert len(AnnualBilling.query.all()) == 0
    with pytest.raises(expected_exception=SQLAlchemyError):
        admin_request.post("service.create_service", _data=data)

    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 0
    assert len(Service.query.filter(Service.name == "created service").all()) == 0


def test_should_not_create_service_with_missing_user_id_field(notify_api, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_from": "service",
                "name": "created service",
                "message_limit": 1000,
                "restricted": False,
                "active": False,
                "created_by": str(fake_uuid),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 400
            assert json_resp["result"] == "error"
            assert "Missing data for required field." in json_resp["message"]["user_id"]


def test_should_error_if_created_by_missing(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_from": "service",
                "name": "created service",
                "message_limit": 1000,
                "restricted": False,
                "active": False,
                "user_id": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 400
            assert json_resp["result"] == "error"
            assert "Missing data for required field." in json_resp["message"]["created_by"]


def test_should_not_create_service_with_missing_if_user_id_is_not_in_database(notify_api, notify_db_session, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_from": "service",
                "user_id": fake_uuid,
                "name": "created service",
                "message_limit": 1000,
                "restricted": False,
                "active": False,
                "created_by": str(fake_uuid),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 404
            assert json_resp["result"] == "error"
            assert json_resp["message"] == "No result found"


def test_should_not_create_service_if_missing_data(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {"user_id": str(sample_user.id)}
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 400
            assert json_resp["result"] == "error"
            assert "Missing data for required field." in json_resp["message"]["name"]
            assert "Missing data for required field." in json_resp["message"]["message_limit"]
            assert "Missing data for required field." in json_resp["message"]["restricted"]


def test_should_not_create_service_with_duplicate_name(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "name": sample_service.name,
                "user_id": str(sample_service.users[0].id),
                "message_limit": 1000,
                "restricted": False,
                "active": False,
                "email_from": "sample.service2",
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert "Duplicate service name '{}'".format(sample_service.name) in json_resp["message"]["name"]


def test_create_service_should_throw_duplicate_key_constraint_for_existing_email_from(
    notify_api, service_factory, sample_user
):
    first_service = service_factory.get("First service", email_from="first.service")
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "First SERVICE"
            data = {
                "name": service_name,
                "user_id": str(first_service.users[0].id),
                "message_limit": 1000,
                "restricted": False,
                "active": False,
                "email_from": "first.service",
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert "Duplicate service name '{}'".format(service_name) in json_resp["message"]["name"]


@pytest.mark.parametrize(
    "email_from, should_error",
    (
        ("sams.sarnies", False),  # We are happy with plain ascii alnum/full-stops.
        ("SAMS.SARNIES", True),  # We will reject anything with uppercase characters
        ("sam's.sarnies", True),  # We reject punctuation other than a full-stop `.`
        ("sams.Бутерброды", True),  # We reject unicode outside of the ascii charset
        ("sams.ü", True),  # Even if it could theoretically be downcast to ascii
        ("sams.u", False),  # Like this, which would be fine
    ),
)
def test_create_service_allows_only_lowercase_digits_and_fullstops_in_email_from(
    admin_request, service_factory, sample_user, email_from, should_error
):
    first_service = service_factory.get("First service", email_from="first.service")
    service_name = "First SERVICE"
    data = {
        "name": service_name,
        "user_id": str(first_service.users[0].id),
        "message_limit": 1000,
        "restricted": False,
        "active": False,
        "email_from": email_from,
        "created_by": str(sample_user.id),
    }
    json_resp = admin_request.post("service.create_service", _data=data, _expected_status=400 if should_error else 201)

    if should_error:
        assert json_resp["result"] == "error"
        assert (
            "Unacceptable characters: `email_from` may only contain letters, numbers and full stops."
            in json_resp["message"]["email_from"]
        )


def test_update_service(client, notify_db_session, sample_service):
    data = {
        "name": "updated service name",
        "email_from": "updated.service.name",
        "created_by": str(sample_service.created_by.id),
        "organisation_type": "school_or_college",
    }

    auth_header = create_admin_authorization_header()

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json
    assert resp.status_code == 200
    assert result["data"]["name"] == "updated service name"
    assert result["data"]["email_from"] == "updated.service.name"
    assert result["data"]["organisation_type"] == "school_or_college"


def test_cant_update_service_org_type_to_random_value(client, sample_service):
    data = {
        "name": "updated service name",
        "email_from": "updated.service.name",
        "created_by": str(sample_service.created_by.id),
        "organisation_type": "foo",
    }

    auth_header = create_admin_authorization_header()

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 500


def test_update_service_flags(client, sample_service):
    auth_header = create_admin_authorization_header()
    resp = client.get("/service/{}".format(sample_service.id), headers=[auth_header])
    json_resp = resp.json
    assert resp.status_code == 200
    assert json_resp["data"]["name"] == sample_service.name
    assert json_resp["data"]["research_mode"] is False

    data = {"research_mode": True, "permissions": [LETTER_TYPE, INTERNATIONAL_SMS_TYPE]}

    auth_header = create_admin_authorization_header()

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json
    assert resp.status_code == 200
    assert result["data"]["research_mode"] is True
    assert set(result["data"]["permissions"]) == set([LETTER_TYPE, INTERNATIONAL_SMS_TYPE])


@pytest.mark.parametrize(
    "field",
    (
        "volume_email",
        "volume_sms",
        "volume_letter",
    ),
)
@pytest.mark.parametrize(
    "value, expected_status, expected_persisted",
    (
        (1234, 200, 1234),
        (None, 200, None),
        ("Aa", 400, None),
    ),
)
def test_update_service_sets_volumes(
    admin_request,
    sample_service,
    field,
    value,
    expected_status,
    expected_persisted,
):
    admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={
            field: value,
        },
        _expected_status=expected_status,
    )
    assert getattr(sample_service, field) == expected_persisted


@pytest.mark.parametrize(
    "value, expected_status, expected_persisted",
    (
        (True, 200, True),
        (False, 200, False),
        ("unknown", 400, None),
    ),
)
def test_update_service_sets_research_consent(
    admin_request,
    sample_service,
    value,
    expected_status,
    expected_persisted,
):
    assert sample_service.consent_to_research is None
    admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={
            "consent_to_research": value,
        },
        _expected_status=expected_status,
    )
    assert sample_service.consent_to_research is expected_persisted


@pytest.fixture(scope="function")
def service_with_no_permissions(notify_db_session):
    return create_service(service_permissions=[])


def test_update_service_flags_with_service_without_default_service_permissions(client, service_with_no_permissions):
    auth_header = create_admin_authorization_header()
    data = {
        "permissions": [LETTER_TYPE, INTERNATIONAL_SMS_TYPE],
    }

    resp = client.post(
        "/service/{}".format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([LETTER_TYPE, INTERNATIONAL_SMS_TYPE])


def test_update_service_flags_will_remove_service_permissions(client, notify_db_session):
    auth_header = create_admin_authorization_header()

    service = create_service(service_permissions=[SMS_TYPE, EMAIL_TYPE, INTERNATIONAL_SMS_TYPE])

    assert INTERNATIONAL_SMS_TYPE in [p.permission for p in service.permissions]

    data = {"permissions": [SMS_TYPE, EMAIL_TYPE]}

    resp = client.post(
        "/service/{}".format(service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert INTERNATIONAL_SMS_TYPE not in result["data"]["permissions"]

    permissions = ServicePermission.query.filter_by(service_id=service.id).all()
    assert set([p.permission for p in permissions]) == set([SMS_TYPE, EMAIL_TYPE])


def test_update_permissions_will_override_permission_flags(client, service_with_no_permissions):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [LETTER_TYPE, INTERNATIONAL_SMS_TYPE]}

    resp = client.post(
        "/service/{}".format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([LETTER_TYPE, INTERNATIONAL_SMS_TYPE])


def test_update_service_permissions_will_add_service_permissions(client, sample_service):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE]}

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([SMS_TYPE, EMAIL_TYPE, LETTER_TYPE])


@pytest.mark.parametrize(
    "email_from, should_error",
    (
        ("sams.sarnies", False),  # We are happy with plain ascii alnum/full-stops.
        ("SAMS.SARNIES", True),  # We will reject anything with uppercase characters
        ("sam's.sarnies", True),  # We reject punctuation other than a full-stop `.`
        ("sams.Бутерброды", True),  # We reject unicode outside of the ascii charset
        ("sams.ü", True),  # Even if it could theoretically be downcast to ascii
        ("sams.u", False),  # Like this, which would be fine
    ),
)
def test_update_service_allows_only_lowercase_digits_and_fullstops_in_email_from(
    admin_request, sample_service, email_from, should_error
):
    data = {"service_name": "Sam's sarnies", "email_from": email_from}

    result = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400 if should_error else 200,
    )

    if should_error:
        assert result["result"] == "error"
        assert (
            "Unacceptable characters: `email_from` may only contain letters, numbers and full stops."
            in result["message"]["email_from"]
        )


@pytest.mark.parametrize(
    "permission_to_add",
    [
        (EMAIL_TYPE),
        (SMS_TYPE),
        (INTERNATIONAL_SMS_TYPE),
        (LETTER_TYPE),
        (INBOUND_SMS_TYPE),
        (EMAIL_AUTH_TYPE),
        (BROADCAST_TYPE),  # TODO: remove this ability to set broadcast permission this way
    ],
)
def test_add_service_permission_will_add_permission(client, service_with_no_permissions, permission_to_add):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [permission_to_add]}

    resp = client.post(
        "/service/{}".format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    permissions = ServicePermission.query.filter_by(service_id=service_with_no_permissions.id).all()

    assert resp.status_code == 200
    assert [p.permission for p in permissions] == [permission_to_add]


def test_update_permissions_with_an_invalid_permission_will_raise_error(client, sample_service):
    auth_header = create_admin_authorization_header()
    invalid_permission = "invalid_permission"

    data = {"permissions": [EMAIL_TYPE, SMS_TYPE, invalid_permission]}

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 400
    assert result["result"] == "error"
    assert "Invalid Service Permission: '{}'".format(invalid_permission) in result["message"]["permissions"]


def test_update_permissions_with_duplicate_permissions_will_raise_error(client, sample_service):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, LETTER_TYPE]}

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 400
    assert result["result"] == "error"
    assert "Duplicate Service Permission: ['{}']".format(LETTER_TYPE) in result["message"]["permissions"]


def test_update_service_research_mode_throws_validation_error(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_admin_authorization_header()
            resp = client.get("/service/{}".format(sample_service.id), headers=[auth_header])
            json_resp = resp.json
            assert resp.status_code == 200
            assert json_resp["data"]["name"] == sample_service.name
            assert not json_resp["data"]["research_mode"]

            data = {"research_mode": "dedede"}

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}".format(sample_service.id),
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            result = resp.json
            assert result["message"]["research_mode"][0] == "Not a valid boolean."
            assert resp.status_code == 400


def test_should_not_update_service_with_duplicate_name(notify_api, notify_db_session, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "another name"
            service = create_service(service_name=service_name, user=sample_user, email_from="another.name")
            data = {"name": service_name, "created_by": str(service.created_by.id)}

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}".format(sample_service.id),
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 400
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert "Duplicate service name '{}'".format(service_name) in json_resp["message"]["name"]


def test_should_not_update_service_with_duplicate_email_from(
    notify_api, notify_db_session, sample_user, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            email_from = "duplicate.name"
            service_name = "duplicate name"
            service = create_service(service_name=service_name, user=sample_user, email_from=email_from)
            data = {"name": service_name, "email_from": email_from, "created_by": str(service.created_by.id)}

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}".format(sample_service.id),
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 400
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert (
                "Duplicate service name '{}'".format(service_name) in json_resp["message"]["name"]
                or "Duplicate service name '{}'".format(email_from) in json_resp["message"]["name"]
            )


def test_update_service_should_404_if_id_is_invalid(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {"name": "updated service name"}

            missing_service_id = uuid.uuid4()

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}".format(missing_service_id),
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 404


def test_get_users_by_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_on_service = sample_service.users[0]
            auth_header = create_admin_authorization_header()

            resp = client.get(
                "/service/{}/users".format(sample_service.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            result = resp.json
            assert len(result["data"]) == 1
            assert result["data"][0]["name"] == user_on_service.name
            assert result["data"][0]["email_address"] == user_on_service.email_address
            assert result["data"][0]["mobile_number"] == user_on_service.mobile_number


def test_get_users_for_service_returns_empty_list_if_no_users_associated_with_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            dao_remove_user_from_service(sample_service, sample_service.users[0])
            auth_header = create_admin_authorization_header()

            response = client.get(
                "/service/{}/users".format(sample_service.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            result = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert result["data"] == []


def test_get_users_for_service_returns_404_when_service_does_not_exist(notify_api, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = uuid.uuid4()
            auth_header = create_admin_authorization_header()

            response = client.get(
                "/service/{}/users".format(service_id), headers=[("Content-Type", "application/json"), auth_header]
            )
            assert response.status_code == 404
            result = json.loads(response.get_data(as_text=True))
            assert result["result"] == "error"
            assert result["message"] == "No result found"


def test_default_permissions_are_added_for_user_service(notify_api, notify_db_session, sample_service, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "name": "created service",
                "user_id": str(sample_user.id),
                "message_limit": 1000,
                "restricted": False,
                "active": False,
                "email_from": "created.service",
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 201
            assert json_resp["data"]["id"]
            assert json_resp["data"]["name"] == "created service"
            assert json_resp["data"]["email_from"] == "created.service"

            auth_header_fetch = create_admin_authorization_header()

            resp = client.get(
                "/service/{}?user_id={}".format(json_resp["data"]["id"], sample_user.id), headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            header = create_admin_authorization_header()
            response = client.get(url_for("user.get_user", user_id=sample_user.id), headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            service_permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            from app.dao.permissions_dao import default_service_permissions

            assert sorted(default_service_permissions) == sorted(service_permissions)


def test_add_existing_user_to_another_service_with_all_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # check which users part of service
            user_already_in_service = sample_service.users[0]
            auth_header = create_admin_authorization_header()

            resp = client.get(
                "/service/{}/users".format(sample_service.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            result = resp.json
            assert len(result["data"]) == 1
            assert result["data"][0]["email_address"] == user_already_in_service.email_address

            # add new user to service
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.cabinet-office.gov.uk",
                password="password",
                mobile_number="+4477123456",
            )
            # they must exist in db first
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": "send_emails"},
                    {"permission": "send_letters"},
                    {"permission": "send_texts"},
                    {"permission": "manage_users"},
                    {"permission": "manage_settings"},
                    {"permission": "manage_api_keys"},
                    {"permission": "manage_templates"},
                    {"permission": "view_activity"},
                ],
                "folder_permissions": [],
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check new user added to service
            auth_header = create_admin_authorization_header()

            resp = client.get(
                "/service/{}".format(sample_service.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 200
            json_resp = resp.json

            # check user has all permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json
            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = [
                "send_texts",
                "send_emails",
                "send_letters",
                "manage_users",
                "manage_settings",
                "manage_templates",
                "manage_api_keys",
                "view_activity",
            ]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_send_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.cabinet-office.gov.uk",
                password="password",
                mobile_number="+4477123456",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": "send_emails"},
                    {"permission": "send_letters"},
                    {"permission": "send_texts"},
                ],
                "folder_permissions": [],
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json

            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = ["send_texts", "send_emails", "send_letters"]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_manage_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.cabinet-office.gov.uk",
                password="password",
                mobile_number="+4477123456",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": "manage_users"},
                    {"permission": "manage_settings"},
                    {"permission": "manage_templates"},
                ]
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json

            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = ["manage_users", "manage_settings", "manage_templates"]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_folder_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.cabinet-office.gov.uk",
                password="password",
                mobile_number="+4477123456",
            )
            save_model_user(user_to_add, validated_email_access=True)

            folder_1 = create_template_folder(sample_service)
            folder_2 = create_template_folder(sample_service)

            data = {
                "permissions": [{"permission": "manage_api_keys"}],
                "folder_permissions": [str(folder_1.id), str(folder_2.id)],
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            new_user = dao_get_service_user(user_id=user_to_add.id, service_id=sample_service.id)

            assert len(new_user.folders) == 2
            assert folder_1 in new_user.folders
            assert folder_2 in new_user.folders


def test_add_existing_user_to_another_service_with_manage_api_keys(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.cabinet-office.gov.uk",
                password="password",
                mobile_number="+4477123456",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {"permissions": [{"permission": "manage_api_keys"}]}

            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json

            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = ["manage_api_keys"]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_non_existing_service_returns404(notify_api, notify_db_session, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.cabinet-office.gov.uk",
                password="password",
                mobile_number="+4477123456",
            )
            save_model_user(user_to_add, validated_email_access=True)

            incorrect_id = uuid.uuid4()

            data = {"permissions": ["send_messages", "manage_service", "manage_api_keys"]}
            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(incorrect_id, user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            result = resp.json
            expected_message = "No result found"

            assert resp.status_code == 404
            assert result["result"] == "error"
            assert result["message"] == expected_message


def test_add_existing_user_of_service_to_service_returns400(notify_api, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            existing_user_id = sample_service.users[0].id

            data = {"permissions": ["send_messages", "manage_service", "manage_api_keys"]}
            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, existing_user_id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            result = resp.json
            expected_message = "User id: {} already part of service id: {}".format(existing_user_id, sample_service.id)

            assert resp.status_code == 400
            assert result["result"] == "error"
            assert result["message"] == expected_message


def test_add_unknown_user_to_service_returns404(notify_api, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            incorrect_id = 9876

            data = {"permissions": ["send_messages", "manage_service", "manage_api_keys"]}
            auth_header = create_admin_authorization_header()

            resp = client.post(
                "/service/{}/users/{}".format(sample_service.id, incorrect_id),
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            result = resp.json
            expected_message = "No result found"

            assert resp.status_code == 404
            assert result["result"] == "error"
            assert result["message"] == expected_message


def test_remove_user_from_service(client, sample_user_service_permission):
    second_user = create_user(email="new@digital.cabinet-office.gov.uk")
    service = sample_user_service_permission.service

    # Simulates successfully adding a user to the service
    dao_add_user_to_service(
        service,
        second_user,
        permissions=[Permission(service_id=service.id, user_id=second_user.id, permission="manage_settings")],
    )

    endpoint = url_for("service.remove_user_from_service", service_id=str(service.id), user_id=str(second_user.id))
    auth_header = create_admin_authorization_header()
    resp = client.delete(endpoint, headers=[("Content-Type", "application/json"), auth_header])
    assert resp.status_code == 204


def test_remove_non_existant_user_from_service(client, sample_user_service_permission):
    second_user = create_user(email="new@digital.cabinet-office.gov.uk")
    endpoint = url_for(
        "service.remove_user_from_service",
        service_id=str(sample_user_service_permission.service.id),
        user_id=str(second_user.id),
    )
    auth_header = create_admin_authorization_header()
    resp = client.delete(endpoint, headers=[("Content-Type", "application/json"), auth_header])
    assert resp.status_code == 404


def test_cannot_remove_only_user_from_service(notify_api, notify_db_session, sample_user_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            endpoint = url_for(
                "service.remove_user_from_service",
                service_id=str(sample_user_service_permission.service.id),
                user_id=str(sample_user_service_permission.user.id),
            )
            auth_header = create_admin_authorization_header()
            resp = client.delete(endpoint, headers=[("Content-Type", "application/json"), auth_header])
            assert resp.status_code == 400
            result = resp.json
            assert result["message"] == "You cannot remove the only user for a service"


# This test is just here verify get_service_and_api_key_history that is a temp solution
# until proper ui is sorted out on admin app
def test_get_service_and_api_key_history(notify_api, sample_service, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_admin_authorization_header()
            response = client.get(path="/service/{}/history".format(sample_service.id), headers=[auth_header])
            assert response.status_code == 200

            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp["data"]["service_history"][0]["id"] == str(sample_service.id)
            assert json_resp["data"]["api_key_history"][0]["id"] == str(sample_api_key.id)


@pytest.mark.parametrize(
    "should_prefix",
    [
        True,
        False,
    ],
)
def test_prefixing_messages_based_on_prefix_sms(
    client,
    notify_db_session,
    should_prefix,
):
    service = create_service(prefix_sms=should_prefix)

    result = client.get(
        url_for("service.get_service_by_id", service_id=service.id),
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    service = json.loads(result.get_data(as_text=True))["data"]
    assert service["prefix_sms"] == should_prefix


@pytest.mark.parametrize(
    "posted_value, stored_value, returned_value",
    [
        (True, True, True),
        (False, False, False),
    ],
)
def test_set_sms_prefixing_for_service(
    admin_request,
    client,
    sample_service,
    posted_value,
    stored_value,
    returned_value,
):
    result = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={"prefix_sms": posted_value},
    )
    assert result["data"]["prefix_sms"] == stored_value


def test_set_sms_prefixing_for_service_cant_be_none(
    admin_request,
    sample_service,
):
    resp = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={"prefix_sms": None},
        _expected_status=400,
    )
    assert resp["message"] == {"prefix_sms": ["Field may not be null."]}


def test_update_service_calls_send_notification_as_service_becomes_live(notify_db_session, client, mocker):
    send_notification_mock = mocker.patch("app.service.rest.send_notification_to_service_users")

    restricted_service = create_service(restricted=True)

    data = {"restricted": False}

    auth_header = create_admin_authorization_header()
    resp = client.post(
        "service/{}".format(restricted_service.id),
        data=json.dumps(data),
        headers=[auth_header],
        content_type="application/json",
    )

    assert resp.status_code == 200
    send_notification_mock.assert_called_once_with(
        service_id=restricted_service.id,
        template_id="9e10c154-d989-4cfe-80ca-481cd09b7251",
        personalisation={"service_name": restricted_service.name, "message_limit": "1,000"},
        include_user_fields=["name"],
    )


def test_update_service_does_not_call_send_notification_for_live_service(sample_service, client, mocker):
    send_notification_mock = mocker.patch("app.service.rest.send_notification_to_service_users")

    data = {"restricted": True}

    auth_header = create_admin_authorization_header()
    resp = client.post(
        "service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[auth_header],
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert not send_notification_mock.called


def test_update_service_does_not_call_send_notification_when_restricted_not_changed(sample_service, client, mocker):
    send_notification_mock = mocker.patch("app.service.rest.send_notification_to_service_users")

    data = {"name": "Name of service"}

    auth_header = create_admin_authorization_header()
    resp = client.post(
        "service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[auth_header],
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert not send_notification_mock.called


def test_get_email_reply_to_addresses_when_there_are_no_reply_to_email_addresses(client, sample_service):
    response = client.get(
        "/service/{}/email-reply-to".format(sample_service.id), headers=[create_admin_authorization_header()]
    )

    assert json.loads(response.get_data(as_text=True)) == []
    assert response.status_code == 200


def test_get_email_reply_to_addresses_with_one_email_address(client, notify_db_session):
    service = create_service()
    create_reply_to_email(service, "test@mail.com")

    response = client.get(
        "/service/{}/email-reply-to".format(service.id), headers=[create_admin_authorization_header()]
    )
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 1
    assert json_response[0]["email_address"] == "test@mail.com"
    assert json_response[0]["is_default"]
    assert json_response[0]["created_at"]
    assert not json_response[0]["updated_at"]
    assert response.status_code == 200


def test_get_email_reply_to_addresses_with_multiple_email_addresses(client, notify_db_session):
    service = create_service()
    reply_to_a = create_reply_to_email(service, "test_a@mail.com")
    reply_to_b = create_reply_to_email(service, "test_b@mail.com", False)

    response = client.get(
        "/service/{}/email-reply-to".format(service.id), headers=[create_admin_authorization_header()]
    )
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 2
    assert response.status_code == 200

    assert json_response[0]["id"] == str(reply_to_a.id)
    assert json_response[0]["service_id"] == str(reply_to_a.service_id)
    assert json_response[0]["email_address"] == "test_a@mail.com"
    assert json_response[0]["is_default"]
    assert json_response[0]["created_at"]
    assert not json_response[0]["updated_at"]

    assert json_response[1]["id"] == str(reply_to_b.id)
    assert json_response[1]["service_id"] == str(reply_to_b.service_id)
    assert json_response[1]["email_address"] == "test_b@mail.com"
    assert not json_response[1]["is_default"]
    assert json_response[1]["created_at"]
    assert not json_response[1]["updated_at"]


def test_add_service_reply_to_email_address(admin_request, sample_service):
    data = {"email_address": "new@reply.com", "is_default": True}
    response = admin_request.post(
        "service.add_service_reply_to_email_address", service_id=sample_service.id, _data=data, _expected_status=201
    )

    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 1
    assert response["data"] == results[0].serialize()


def test_add_service_reply_to_email_address_doesnt_allow_duplicates(admin_request, notify_db_session, mocker):
    data = {"email_address": "reply-here@example.gov.uk", "is_default": True}
    service = create_service()
    create_reply_to_email(service, "reply-here@example.gov.uk")
    response = admin_request.post(
        "service.add_service_reply_to_email_address", service_id=service.id, _data=data, _expected_status=409
    )
    assert response["message"] == "Your service already uses ‘reply-here@example.gov.uk’ as an email reply-to address."


def test_add_service_reply_to_email_address_can_add_multiple_addresses(admin_request, sample_service):
    data = {"email_address": "first@reply.com", "is_default": True}
    admin_request.post(
        "service.add_service_reply_to_email_address", service_id=sample_service.id, _data=data, _expected_status=201
    )
    second = {"email_address": "second@reply.com", "is_default": True}
    response = admin_request.post(
        "service.add_service_reply_to_email_address", service_id=sample_service.id, _data=second, _expected_status=201
    )
    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 2
    default = [x for x in results if x.is_default]
    assert response["data"] == default[0].serialize()
    first_reply_to_not_default = [x for x in results if not x.is_default]
    assert first_reply_to_not_default[0].email_address == "first@reply.com"


def test_add_service_reply_to_email_address_raise_exception_if_no_default(admin_request, sample_service):
    data = {"email_address": "first@reply.com", "is_default": False}
    response = admin_request.post(
        "service.add_service_reply_to_email_address", service_id=sample_service.id, _data=data, _expected_status=400
    )
    assert response["message"] == "You must have at least one reply to email address as the default."


def test_add_service_reply_to_email_address_404s_when_invalid_service_id(admin_request, notify_db_session):
    response = admin_request.post(
        "service.add_service_reply_to_email_address", service_id=uuid.uuid4(), _data={}, _expected_status=404
    )

    assert response["result"] == "error"
    assert response["message"] == "No result found"


def test_update_service_reply_to_email_address(admin_request, sample_service):
    original_reply_to = create_reply_to_email(service=sample_service, email_address="some@email.com")
    data = {"email_address": "changed@reply.com", "is_default": True}
    response = admin_request.post(
        "service.update_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=original_reply_to.id,
        _data=data,
        _expected_status=200,
    )

    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 1
    assert response["data"] == results[0].serialize()


def test_update_service_reply_to_email_address_returns_400_when_no_default(admin_request, sample_service):
    original_reply_to = create_reply_to_email(service=sample_service, email_address="some@email.com")
    data = {"email_address": "changed@reply.com", "is_default": False}
    response = admin_request.post(
        "service.update_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=original_reply_to.id,
        _data=data,
        _expected_status=400,
    )

    assert response["message"] == "You must have at least one reply to email address as the default."


def test_update_service_reply_to_email_address_404s_when_invalid_service_id(admin_request, notify_db_session):
    response = admin_request.post(
        "service.update_service_reply_to_email_address",
        service_id=uuid.uuid4(),
        reply_to_email_id=uuid.uuid4(),
        _data={},
        _expected_status=404,
    )

    assert response["result"] == "error"
    assert response["message"] == "No result found"


def test_delete_service_reply_to_email_address_archives_an_email_reply_to(
    sample_service, admin_request, notify_db_session
):
    create_reply_to_email(service=sample_service, email_address="some@email.com")
    reply_to = create_reply_to_email(service=sample_service, email_address="some@email.com", is_default=False)

    admin_request.post(
        "service.delete_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=reply_to.id,
    )
    assert reply_to.archived is True


def test_delete_service_reply_to_email_address_returns_400_if_archiving_default_reply_to(
    admin_request, notify_db_session, sample_service
):
    reply_to = create_reply_to_email(service=sample_service, email_address="some@email.com")

    response = admin_request.post(
        "service.delete_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=reply_to.id,
        _expected_status=400,
    )

    assert response == {"message": "You cannot delete a default email reply to address", "result": "error"}
    assert reply_to.archived is False


def test_get_email_reply_to_address(client, notify_db_session):
    service = create_service()
    reply_to = create_reply_to_email(service, "test_a@mail.com")

    response = client.get(
        "/service/{}/email-reply-to/{}".format(service.id, reply_to.id),
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == reply_to.serialize()


def test_get_letter_contacts_when_there_are_no_letter_contacts(client, sample_service):
    response = client.get(
        "/service/{}/letter-contact".format(sample_service.id), headers=[create_admin_authorization_header()]
    )

    assert json.loads(response.get_data(as_text=True)) == []
    assert response.status_code == 200


def test_get_letter_contacts_with_one_letter_contact(client, notify_db_session):
    service = create_service()
    create_letter_contact(service, "Aberdeen, AB23 1XH")

    response = client.get(
        "/service/{}/letter-contact".format(service.id), headers=[create_admin_authorization_header()]
    )
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 1
    assert json_response[0]["contact_block"] == "Aberdeen, AB23 1XH"
    assert json_response[0]["is_default"]
    assert json_response[0]["created_at"]
    assert not json_response[0]["updated_at"]
    assert response.status_code == 200


def test_get_letter_contacts_with_multiple_letter_contacts(client, notify_db_session):
    service = create_service()
    letter_contact_a = create_letter_contact(service, "Aberdeen, AB23 1XH")
    letter_contact_b = create_letter_contact(service, "London, E1 8QS", False)

    response = client.get(
        "/service/{}/letter-contact".format(service.id), headers=[create_admin_authorization_header()]
    )
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 2
    assert response.status_code == 200

    assert json_response[0]["id"] == str(letter_contact_a.id)
    assert json_response[0]["service_id"] == str(letter_contact_a.service_id)
    assert json_response[0]["contact_block"] == "Aberdeen, AB23 1XH"
    assert json_response[0]["is_default"]
    assert json_response[0]["created_at"]
    assert not json_response[0]["updated_at"]

    assert json_response[1]["id"] == str(letter_contact_b.id)
    assert json_response[1]["service_id"] == str(letter_contact_b.service_id)
    assert json_response[1]["contact_block"] == "London, E1 8QS"
    assert not json_response[1]["is_default"]
    assert json_response[1]["created_at"]
    assert not json_response[1]["updated_at"]


def test_get_letter_contact_by_id(client, notify_db_session):
    service = create_service()
    letter_contact = create_letter_contact(service, "London, E1 8QS")

    response = client.get(
        "/service/{}/letter-contact/{}".format(service.id, letter_contact.id),
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == letter_contact.serialize()


def test_get_letter_contact_return_404_when_invalid_contact_id(client, notify_db_session):
    service = create_service()

    response = client.get(
        "/service/{}/letter-contact/{}".format(service.id, "93d59f88-4aa1-453c-9900-f61e2fc8a2de"),
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 404


def test_add_service_contact_block(client, sample_service):
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": True})
    response = client.post(
        "/service/{}/letter-contact".format(sample_service.id),
        data=data,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceLetterContact.query.all()
    assert len(results) == 1
    assert json_resp["data"] == results[0].serialize()


def test_add_service_letter_contact_can_add_multiple_addresses(client, sample_service):
    first = json.dumps({"contact_block": "London, E1 8QS", "is_default": True})
    client.post(
        "/service/{}/letter-contact".format(sample_service.id),
        data=first,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    second = json.dumps({"contact_block": "Aberdeen, AB23 1XH", "is_default": True})
    response = client.post(
        "/service/{}/letter-contact".format(sample_service.id),
        data=second,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceLetterContact.query.all()
    assert len(results) == 2
    default = [x for x in results if x.is_default]
    assert json_resp["data"] == default[0].serialize()
    first_letter_contact_not_default = [x for x in results if not x.is_default]
    assert first_letter_contact_not_default[0].contact_block == "London, E1 8QS"


def test_add_service_letter_contact_block_fine_if_no_default(client, sample_service):
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": False})
    response = client.post(
        "/service/{}/letter-contact".format(sample_service.id),
        data=data,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert response.status_code == 201


def test_add_service_letter_contact_block_404s_when_invalid_service_id(client, notify_db_session):
    response = client.post(
        "/service/{}/letter-contact".format(uuid.uuid4()),
        data={},
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result["result"] == "error"
    assert result["message"] == "No result found"


def test_update_service_letter_contact(client, sample_service):
    original_letter_contact = create_letter_contact(service=sample_service, contact_block="Aberdeen, AB23 1XH")
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": True})
    response = client.post(
        "/service/{}/letter-contact/{}".format(sample_service.id, original_letter_contact.id),
        data=data,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceLetterContact.query.all()
    assert len(results) == 1
    assert json_resp["data"] == results[0].serialize()


def test_update_service_letter_contact_returns_200_when_no_default(client, sample_service):
    original_reply_to = create_letter_contact(service=sample_service, contact_block="Aberdeen, AB23 1XH")
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": False})
    response = client.post(
        "/service/{}/letter-contact/{}".format(sample_service.id, original_reply_to.id),
        data=data,
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )
    assert response.status_code == 200


def test_update_service_letter_contact_returns_404_when_invalid_service_id(client, notify_db_session):
    response = client.post(
        "/service/{}/letter-contact/{}".format(uuid.uuid4(), uuid.uuid4()),
        data={},
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
    )

    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result["result"] == "error"
    assert result["message"] == "No result found"


def test_delete_service_letter_contact_can_archive_letter_contact(admin_request, notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block="Edinburgh, ED1 1AA")
    letter_contact = create_letter_contact(service=service, contact_block="Swansea, SN1 3CC", is_default=False)

    admin_request.post(
        "service.delete_service_letter_contact",
        service_id=service.id,
        letter_contact_id=letter_contact.id,
    )

    assert letter_contact.archived is True


def test_delete_service_letter_contact_returns_200_if_archiving_template_default(admin_request, notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block="Edinburgh, ED1 1AA")
    letter_contact = create_letter_contact(service=service, contact_block="Swansea, SN1 3CC", is_default=False)
    create_template(service=service, template_type="letter", reply_to=letter_contact.id)

    response = admin_request.post(
        "service.delete_service_letter_contact",
        service_id=service.id,
        letter_contact_id=letter_contact.id,
        _expected_status=200,
    )
    assert response["data"]["archived"] is True


def test_get_organisation_for_service_id(admin_request, sample_service, sample_organisation):
    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    response = admin_request.get("service.get_organisation_for_service", service_id=sample_service.id)
    assert response == sample_organisation.serialize()


def test_get_organisation_for_service_id_return_empty_dict_if_service_not_in_organisation(admin_request, fake_uuid):
    response = admin_request.get("service.get_organisation_for_service", service_id=fake_uuid)
    assert response == {}


@pytest.mark.parametrize("channel", ["operator", "test", "severe", "government"])
def test_set_as_broadcast_service_sets_broadcast_channel(
    admin_request, sample_service, broadcast_organisation, channel
):
    assert sample_service.service_broadcast_settings is None
    data = {
        "broadcast_channel": channel,
        "service_mode": "live",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )
    assert result["data"]["name"] == "Sample service"
    assert result["data"]["broadcast_channel"] == channel

    records = ServiceBroadcastSettings.query.filter_by(service_id=sample_service.id).all()
    assert len(records) == 1
    assert records[0].service_id == sample_service.id
    assert records[0].channel == channel


def test_set_as_broadcast_service_updates_channel_for_broadcast_service(admin_request, sample_broadcast_service):
    assert sample_broadcast_service.broadcast_channel == "severe"

    data = {
        "broadcast_channel": "test",
        "service_mode": "training",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )
    assert result["data"]["name"] == "Sample broadcast service"
    assert result["data"]["broadcast_channel"] == "test"

    records = ServiceBroadcastSettings.query.filter_by(service_id=sample_broadcast_service.id).all()
    assert len(records) == 1
    assert records[0].service_id == sample_broadcast_service.id
    assert records[0].channel == "test"


@pytest.mark.parametrize("channel", ["extreme", "exercise", "random", ""])
def test_set_as_broadcast_service_rejects_unknown_channels(
    admin_request, sample_service, broadcast_organisation, channel
):
    data = {
        "broadcast_channel": channel,
        "service_mode": "live",
        "provider_restriction": "all",
    }

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )


def test_set_as_broadcast_service_rejects_if_no_channel(
    admin_request, notify_db_session, sample_service, broadcast_organisation
):
    data = {
        "service_mode": "training",
        "provider_restriction": "all",
    }

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )


@pytest.mark.parametrize(
    "starting_permissions, ending_permissions",
    (
        ([], [BROADCAST_TYPE]),
        ([EMAIL_AUTH_TYPE], [BROADCAST_TYPE, EMAIL_AUTH_TYPE]),
        ([p for p in SERVICE_PERMISSION_TYPES if p != BROADCAST_TYPE], [BROADCAST_TYPE, EMAIL_AUTH_TYPE]),
    ),
)
def test_set_as_broadcast_service_gives_broadcast_permission_and_removes_other_channel_permissions(
    admin_request, broadcast_organisation, starting_permissions, ending_permissions
):
    sample_service = create_service(service_permissions=starting_permissions)
    data = {
        "broadcast_channel": "severe",
        "service_mode": "training",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )
    assert set(result["data"]["permissions"]) == set(ending_permissions)

    permissions = ServicePermission.query.filter_by(service_id=sample_service.id).all()
    assert set([p.permission for p in permissions]) == set(ending_permissions)


@pytest.mark.parametrize(
    "has_email_auth, ending_permissions",
    (
        (False, [BROADCAST_TYPE]),
        (True, [BROADCAST_TYPE, EMAIL_AUTH_TYPE]),
    ),
)
def test_set_as_broadcast_service_maintains_broadcast_permission_for_existing_broadcast_service(
    admin_request, sample_broadcast_service, has_email_auth, ending_permissions
):
    if has_email_auth:
        service_permission = ServicePermission(service_id=sample_broadcast_service.id, permission=EMAIL_AUTH_TYPE)
        sample_broadcast_service.permissions.append(service_permission)

    current_permissions = [p.permission for p in sample_broadcast_service.permissions]
    assert set(current_permissions) == set(ending_permissions)

    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )
    assert set(result["data"]["permissions"]) == set(ending_permissions)

    permissions = ServicePermission.query.filter_by(service_id=sample_broadcast_service.id).all()
    assert set([p.permission for p in permissions]) == set(ending_permissions)


def test_set_as_broadcast_service_sets_count_as_live_to_false(admin_request, sample_service, broadcast_organisation):
    assert sample_service.count_as_live is True

    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
        "provider_restriction": "all",
    }
    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )
    assert result["data"]["count_as_live"] is False

    service_from_db = Service.query.filter_by(id=sample_service.id).all()[0]
    assert service_from_db.count_as_live is False


def test_set_as_broadcast_service_sets_service_org_to_broadcast_org(
    admin_request, sample_service, broadcast_organisation
):
    assert sample_service.organisation_id != current_app.config["BROADCAST_ORGANISATION_ID"]

    data = {
        "broadcast_channel": "severe",
        "service_mode": "training",
        "provider_restriction": "all",
    }
    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )
    assert result["data"]["organisation"] == current_app.config["BROADCAST_ORGANISATION_ID"]

    service_from_db = Service.query.filter_by(id=sample_service.id).all()[0]
    assert str(service_from_db.organisation_id) == current_app.config["BROADCAST_ORGANISATION_ID"]


def test_set_as_broadcast_service_does_not_error_if_run_on_a_service_that_is_already_a_broadcast_service(
    admin_request, sample_service, broadcast_organisation
):
    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
        "provider_restriction": "all",
    }
    for _ in range(2):
        admin_request.post(
            "service.set_as_broadcast_service",
            service_id=sample_service.id,
            _data=data,
        )


@freeze_time("2021-02-02")
def test_set_as_broadcast_service_sets_service_to_live_mode(
    admin_request, notify_db_session, sample_service, broadcast_organisation
):
    sample_service.restricted = True
    notify_db_session.add(sample_service)
    notify_db_session.commit()
    assert sample_service.restricted is True
    assert sample_service.go_live_at is None
    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )
    assert result["data"]["name"] == "Sample service"
    assert result["data"]["restricted"] is False
    assert result["data"]["go_live_at"] == "2021-02-02 00:00:00.000000"


def test_set_as_broadcast_service_doesnt_override_existing_go_live_at(
    admin_request, notify_db_session, sample_broadcast_service
):
    sample_broadcast_service.restricted = False
    sample_broadcast_service.go_live_at = datetime(2021, 1, 1)
    notify_db_session.add(sample_broadcast_service)
    notify_db_session.commit()
    assert sample_broadcast_service.restricted is False
    assert sample_broadcast_service.go_live_at is not None
    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )
    assert result["data"]["name"] == "Sample broadcast service"
    assert result["data"]["restricted"] is False
    assert result["data"]["go_live_at"] == "2021-01-01 00:00:00.000000"


def test_set_as_broadcast_service_sets_service_to_training_mode(
    admin_request, notify_db_session, sample_broadcast_service
):
    sample_broadcast_service.restricted = False
    sample_broadcast_service.go_live_at = datetime(2021, 1, 1)
    notify_db_session.add(sample_broadcast_service)
    notify_db_session.commit()
    assert sample_broadcast_service.restricted is False
    assert sample_broadcast_service.go_live_at is not None

    data = {
        "broadcast_channel": "severe",
        "service_mode": "training",
        "provider_restriction": "all",
    }

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )
    assert result["data"]["name"] == "Sample broadcast service"
    assert result["data"]["restricted"] is True
    assert result["data"]["go_live_at"] is None


@pytest.mark.parametrize("service_mode", ["testing", ""])
def test_set_as_broadcast_service_rejects_unknown_service_mode(
    admin_request, sample_service, broadcast_organisation, service_mode
):
    data = {
        "broadcast_channel": "severe",
        "service_mode": service_mode,
        "provider_restriction": "all",
    }

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )


def test_set_as_broadcast_service_rejects_if_no_service_mode(admin_request, sample_service, broadcast_organisation):
    data = {
        "broadcast_channel": "severe",
        "provider_restriction": "all",
    }

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )


@pytest.mark.parametrize("provider", ["all", "three", "ee", "vodafone", "o2"])
def test_set_as_broadcast_service_sets_mobile_provider_restriction(
    admin_request, sample_service, broadcast_organisation, provider
):
    assert sample_service.service_broadcast_settings is None
    data = {"broadcast_channel": "severe", "service_mode": "live", "provider_restriction": provider}

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )
    assert result["data"]["name"] == "Sample service"
    assert result["data"]["allowed_broadcast_provider"] == provider

    records = ServiceBroadcastSettings.query.filter_by(service_id=sample_service.id).all()
    assert len(records) == 1
    assert records[0].service_id == sample_service.id
    assert records[0].provider == provider


@pytest.mark.parametrize("provider", ["all", "vodafone"])
def test_set_as_broadcast_service_updates_mobile_provider_restriction(
    admin_request, notify_db_session, sample_broadcast_service, provider
):
    sample_broadcast_service.service_broadcast_settings.provider = "o2"
    notify_db_session.add(sample_broadcast_service)
    notify_db_session.commit()
    assert sample_broadcast_service.service_broadcast_settings.provider == "o2"

    data = {"broadcast_channel": "severe", "service_mode": "live", "provider_restriction": provider}

    result = admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )

    assert result["data"]["name"] == "Sample broadcast service"
    assert result["data"]["allowed_broadcast_provider"] == provider

    records = ServiceBroadcastSettings.query.filter_by(service_id=sample_broadcast_service.id).all()
    assert len(records) == 1
    assert records[0].service_id == sample_broadcast_service.id
    assert records[0].provider == provider


@pytest.mark.parametrize("provider", ["three, o2", "giffgaff", "", "None"])
def test_set_as_broadcast_service_rejects_unknown_provider_restriction(
    admin_request, sample_service, broadcast_organisation, provider
):
    data = {"broadcast_channel": "test", "service_mode": "live", "provider_restriction": provider}

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )


def test_set_as_broadcast_service_errors_if_no_mobile_provider_restriction(
    admin_request, sample_service, broadcast_organisation
):
    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
    }

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )


def test_set_as_broadcast_service_updates_services_history(admin_request, sample_service, broadcast_organisation):
    old_history_records = Service.get_history_model().query.filter_by(id=sample_service.id).all()
    data = {
        "broadcast_channel": "test",
        "service_mode": "live",
        "provider_restriction": "all",
    }

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data=data,
    )

    new_history_records = Service.get_history_model().query.filter_by(id=sample_service.id).all()
    assert len(new_history_records) == len(old_history_records) + 1


def test_set_as_broadcast_service_removes_user_permissions(
    admin_request,
    broadcast_organisation,
    sample_service,
    sample_service_full_permissions,
    sample_invited_user,
):
    service_user = sample_service.users[0]

    # make the user a member of a second service
    dao_add_user_to_service(
        sample_service_full_permissions,
        service_user,
        permissions=[
            Permission(service_id=sample_service_full_permissions.id, user_id=service_user.id, permission="send_emails")
        ],
    )
    assert len(service_user.get_permissions(service_id=sample_service.id)) == 8
    assert len(sample_invited_user.get_permissions()) == 3

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data={"broadcast_channel": "test", "service_mode": "live", "provider_restriction": "ee"},
    )

    # The user permissions for the broadcast service (apart from 'view_activity') get removed
    assert service_user.get_permissions(service_id=sample_service.id) == ["view_activity"]

    # Permissions for users invited to the broadcast service (apart from 'view_activity') get removed
    assert sample_invited_user.permissions == "view_activity"

    # Permissions for other services remain
    assert service_user.get_permissions(service_id=sample_service_full_permissions.id) == ["send_emails"]


@freeze_time("2021-12-21")
def test_set_as_broadcast_service_revokes_api_keys(
    admin_request,
    broadcast_organisation,
    sample_service,
    sample_service_full_permissions,
):
    api_key_1 = create_api_key(service=sample_service)
    api_key_2 = create_api_key(service=sample_service)
    api_key_3 = create_api_key(service=sample_service_full_permissions)

    api_key_2.expiry_date = datetime.utcnow() - timedelta(days=365)

    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_service.id,
        _data={
            "broadcast_channel": "government",
            "service_mode": "live",
            "provider_restriction": "all",
        },
    )

    # This key should have a new expiry date
    assert api_key_1.expiry_date.isoformat().startswith("2021-12-21")

    # This key keeps its old expiry date
    assert api_key_2.expiry_date.isoformat().startswith("2020-12-21")

    # This key is from a different service
    assert api_key_3.expiry_date is None
