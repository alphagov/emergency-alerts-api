import json
import uuid
from datetime import datetime, timedelta

import pytest
from flask import current_app, url_for
from freezegun import freeze_time

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
    SERVICE_PERMISSION_TYPES,
    Permission,
    Service,
    ServiceBroadcastSettings,
    ServicePermission,
    User,
)
from tests import create_admin_authorization_header
from tests.app.db import (
    create_api_key,
    create_domain,
    create_organisation,
    create_service,
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
    assert json_resp["data"]["allowed_broadcast_provider"] is None
    assert json_resp["data"]["broadcast_channel"] is None

    assert set(json_resp["data"].keys()) == {
        "active",
        "allowed_broadcast_provider",
        "broadcast_channel",
        "created_at",
        "created_by",
        "go_live_at",
        "go_live_user",
        "id",
        "inbound_api",
        "name",
        "notes",
        "organisation",
        "organisation_type",
        "permissions",
        "restricted",
        "service_callback_api",
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
    assert all(set(json["permissions"]) == {BROADCAST_TYPE} for json in json_resp["data"])


def test_get_service_by_id_has_default_service_permissions(admin_request, sample_service):
    json_resp = admin_request.get("service.get_service_by_id", service_id=sample_service.id)

    assert set(json_resp["data"]["permissions"]) == {BROADCAST_TYPE}


def test_get_service_by_id_should_404_if_no_service(admin_request, notify_db_session):
    json_resp = admin_request.get("service.get_service_by_id", service_id=uuid.uuid4(), _expected_status=404)

    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_get_service_by_id_and_user(client, sample_service, sample_user):
    sample_service.reply_to_email = "something@service.com"
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
    "platform_admin",
    (
        True,
        False,
    ),
)
def test_create_service(
    admin_request,
    sample_user,
    platform_admin,
):
    sample_user.platform_admin = platform_admin
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "restricted": False,
        "active": False,
        "created_by": str(sample_user.id),
    }

    json_resp = admin_request.post("service.create_service", _data=data, _expected_status=201)

    assert json_resp["data"]["id"]
    assert json_resp["data"]["name"] == "created service"

    service_db = Service.query.get(json_resp["data"]["id"])
    assert service_db.name == "created service"

    json_resp = admin_request.get(
        "service.get_service_by_id", service_id=json_resp["data"]["id"], user_id=sample_user.id
    )

    assert json_resp["data"]["name"] == "created service"


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
        "restricted": False,
        "active": False,
        "created_by": str(sample_user.id),
        "service_domain": domain,
    }

    json_resp = admin_request.post("service.create_service", _data=data, _expected_status=201)

    if expected_org:
        assert json_resp["data"]["organisation"] == str(org.id)
    else:
        assert json_resp["data"]["organisation"] is None


def test_should_not_create_service_with_missing_user_id_field(notify_api, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "name": "created service",
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
                "name": "created service",
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
                "user_id": fake_uuid,
                "name": "created service",
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
            assert "Missing data for required field." in json_resp["message"]["restricted"]


def test_should_not_create_service_with_duplicate_name(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "name": sample_service.name,
                "user_id": str(sample_service.users[0].id),
                "restricted": False,
                "active": False,
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert "Duplicate service name '{}'".format(sample_service.name) in json_resp["message"]["name"]


def test_update_service(client, notify_db_session, sample_service):
    data = {
        "name": "updated service name",
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
    assert result["data"]["organisation_type"] == "school_or_college"


def test_cant_update_service_org_type_to_random_value(client, sample_service):
    data = {
        "name": "updated service name",
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

    data = {"permissions": [BROADCAST_TYPE]}

    auth_header = create_admin_authorization_header()

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json
    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([BROADCAST_TYPE])


@pytest.fixture(scope="function")
def service_with_no_permissions(notify_db_session):
    return create_service(service_permissions=[])


def test_update_service_flags_with_service_without_default_service_permissions(client, service_with_no_permissions):
    auth_header = create_admin_authorization_header()
    data = {
        "permissions": [BROADCAST_TYPE],
    }

    resp = client.post(
        "/service/{}".format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([BROADCAST_TYPE])


def test_update_service_flags_will_remove_service_permissions(client, notify_db_session):
    auth_header = create_admin_authorization_header()

    service = create_service(service_permissions=[BROADCAST_TYPE, EMAIL_AUTH_TYPE])

    assert EMAIL_AUTH_TYPE in [p.permission for p in service.permissions]

    data = {"permissions": [BROADCAST_TYPE]}

    resp = client.post(
        "/service/{}".format(service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert EMAIL_AUTH_TYPE not in result["data"]["permissions"]

    permissions = ServicePermission.query.filter_by(service_id=service.id).all()
    assert set([p.permission for p in permissions]) == set([BROADCAST_TYPE])


def test_update_permissions_will_override_permission_flags(client, service_with_no_permissions):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [BROADCAST_TYPE, EMAIL_AUTH_TYPE]}

    resp = client.post(
        "/service/{}".format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([BROADCAST_TYPE, EMAIL_AUTH_TYPE])


def test_update_service_permissions_will_add_service_permissions(client, sample_service):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [BROADCAST_TYPE]}

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == set([BROADCAST_TYPE])


@pytest.mark.parametrize(
    "permission_to_add",
    [
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

    data = {"permissions": [BROADCAST_TYPE, invalid_permission]}

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

    data = {"permissions": [BROADCAST_TYPE, BROADCAST_TYPE]}

    resp = client.post(
        "/service/{}".format(sample_service.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 400
    assert result["result"] == "error"
    assert "Duplicate Service Permission: ['{}']".format(BROADCAST_TYPE) in result["message"]["permissions"]


def test_should_not_update_service_with_duplicate_name(notify_api, notify_db_session, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "another name"
            service = create_service(service_name=service_name, user=sample_user)
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
                "restricted": False,
                "active": False,
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 201
            assert json_resp["data"]["id"]
            assert json_resp["data"]["name"] == "created service"

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
                mobile_number="+447712345678",
            )
            # they must exist in db first
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
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
                mobile_number="+447712345678",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": "create_broadcasts"},
                    {"permission": "approve_broadcasts"},
                    {"permission": "reject_broadcasts"},
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
            expected_permissions = ["create_broadcasts", "approve_broadcasts", "reject_broadcasts"]
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
                mobile_number="+447712345678",
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
                mobile_number="+447712345678",
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
                mobile_number="+447712345678",
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
                mobile_number="+447712345678",
            )
            save_model_user(user_to_add, validated_email_access=True)

            incorrect_id = uuid.uuid4()

            data = {"permissions": ["create_broadcasts", "manage_service", "manage_api_keys"]}
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

            data = {"permissions": ["create_broadcasts", "manage_service", "manage_api_keys"]}
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

            data = {"permissions": ["create_broadcasts", "manage_service", "manage_api_keys"]}
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
        personalisation={"service_name": restricted_service.name},
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
            Permission(
                service_id=sample_service_full_permissions.id, user_id=service_user.id, permission="create_broadcasts"
            )
        ],
    )
    assert len(service_user.get_permissions(service_id=sample_service.id)) == 5
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
    assert service_user.get_permissions(service_id=sample_service_full_permissions.id) == ["create_broadcasts"]


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
