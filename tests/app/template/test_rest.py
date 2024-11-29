import json
import random
import string
import uuid

import pytest
import requests_mock

from app.dao.templates_dao import dao_get_template_by_id
from app.models import (
    BROADCAST_TYPE,
    PLACEHOLDER_TYPE,
    Template,
    TemplateHistory,
)
from tests import create_admin_authorization_header
from tests.app.db import create_service, create_template, create_template_folder

MAX_BROADCAST_CHAR_COUNT = 1395


def test_should_create_a_new_template_for_a_service(client, sample_user):
    service = create_service(service_permissions=[BROADCAST_TYPE])
    data = {
        "name": "my template",
        "template_type": BROADCAST_TYPE,
        "content": "template <b>content</b>",
        "service": str(service.id),
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"]["name"] == "my template"
    assert json_resp["data"]["template_type"] == BROADCAST_TYPE
    assert json_resp["data"]["content"] == "template <b>content</b>"
    assert json_resp["data"]["service"] == str(service.id)
    assert json_resp["data"]["id"]
    assert json_resp["data"]["version"] == 1
    assert json_resp["data"]["created_by"] == str(sample_user.id)

    template = Template.query.get(json_resp["data"]["id"])
    from app.schemas import template_schema

    assert sorted(json_resp["data"]) == sorted(template_schema.dump(template))


def test_create_a_new_template_for_a_service_adds_folder_relationship(client, sample_service):
    parent_folder = create_template_folder(service=sample_service, name="parent folder")

    data = {
        "name": "my template",
        "template_type": "broadcast",
        "content": "template <b>content</b>",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
        "parent_folder_id": str(parent_folder.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    template = Template.query.filter(Template.name == "my template").first()
    assert template.folder == parent_folder


def test_create_template_should_return_400_if_folder_is_for_a_different_service(client, sample_service):
    service2 = create_service(service_name="second service")
    parent_folder = create_template_folder(service=service2)

    data = {
        "name": "my template",
        "template_type": "broadcast",
        "content": "template <b>content</b>",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
        "parent_folder_id": str(parent_folder.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True))["message"] == "parent_folder_id not found"


def test_create_template_should_return_400_if_folder_does_not_exist(client, sample_service):
    data = {
        "name": "my template",
        "template_type": "broadcast",
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
        "parent_folder_id": str(uuid.uuid4()),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True))["message"] == "parent_folder_id not found"


def test_should_raise_error_if_service_does_not_exist_on_create(client, sample_user, fake_uuid):
    data = {
        "name": "my template",
        "template_type": BROADCAST_TYPE,
        "content": "template content",
        "service": fake_uuid,
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(fake_uuid), headers=[("Content-Type", "application/json"), auth_header], data=data
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


@pytest.mark.parametrize(
    "permissions, template_type, expected_error",
    [
        (
            [PLACEHOLDER_TYPE],
            BROADCAST_TYPE,
            {"template_type": ["Creating broadcast message templates is not allowed"]},
        ),
    ],
)
def test_should_raise_error_on_create_if_no_permission(client, sample_user, permissions, template_type, expected_error):
    service = create_service(service_permissions=permissions)
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template content",
        "service": str(service.id),
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 403
    assert json_resp["result"] == "error"
    assert json_resp["message"] == expected_error


@pytest.mark.parametrize(
    "template_type, permissions, expected_error",
    [
        (
            BROADCAST_TYPE,
            [PLACEHOLDER_TYPE],
            {"template_type": ["Updating broadcast message templates is not allowed"]},
        ),
    ],
)
def test_should_be_error_on_update_if_no_permission(
    client,
    sample_user,
    notify_db_session,
    template_type,
    permissions,
    expected_error,
):
    service = create_service(service_permissions=permissions)
    template_without_permission = create_template(service, template_type=template_type)
    data = {"content": "new template content", "created_by": str(sample_user.id)}

    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    update_response = client.post(
        "/service/{}/template/{}".format(template_without_permission.service_id, template_without_permission.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )

    json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_response.status_code == 403
    assert json_resp["result"] == "error"
    assert json_resp["message"] == expected_error


def test_should_error_if_created_by_missing(client, sample_user, sample_service):
    service_id = str(sample_service.id)
    data = {
        "name": "my template",
        "template_type": BROADCAST_TYPE,
        "content": "template content",
        "service": service_id,
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(service_id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["errors"][0]["error"] == "ValidationError"
    assert json_resp["errors"][0]["message"] == "created_by is a required property"


def test_should_be_error_if_service_does_not_exist_on_update(client, fake_uuid):
    data = {"name": "my template"}
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template/{}".format(fake_uuid, fake_uuid),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_update_should_update_a_template(client, sample_user):
    service = create_service(service_permissions=[BROADCAST_TYPE])
    template = create_template(service, template_type=BROADCAST_TYPE)

    assert template.created_by == service.created_by
    assert template.created_by != sample_user

    data = {"content": "my template has new content", "created_by": str(sample_user.id)}
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    update_response = client.post(
        "/service/{}/template/{}".format(service.id, template.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )

    assert update_response.status_code == 200
    update_json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_json_resp["data"]["content"] == ("my template has new content")
    assert update_json_resp["data"]["name"] == template.name
    assert update_json_resp["data"]["template_type"] == template.template_type
    assert update_json_resp["data"]["version"] == 2

    assert update_json_resp["data"]["created_by"] == str(sample_user.id)
    template_created_by_users = [template.created_by_id for template in TemplateHistory.query.all()]
    assert len(template_created_by_users) == 2
    assert service.created_by.id in template_created_by_users
    assert sample_user.id in template_created_by_users


def test_should_be_able_to_archive_template(client, sample_template):
    data = {
        "name": sample_template.name,
        "template_type": sample_template.template_type,
        "content": sample_template.content,
        "archived": True,
        "service": str(sample_template.service.id),
        "created_by": str(sample_template.created_by.id),
    }

    json_data = json.dumps(data)

    auth_header = create_admin_authorization_header()

    resp = client.post(
        "/service/{}/template/{}".format(sample_template.service.id, sample_template.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=json_data,
    )

    assert resp.status_code == 200
    assert Template.query.first().archived


def test_should_be_able_to_archive_template_should_remove_template_folders(client, sample_service):
    template_folder = create_template_folder(service=sample_service)
    template = create_template(service=sample_service, folder=template_folder)

    data = {
        "archived": True,
    }

    client.post(
        f"/service/{sample_service.id}/template/{template.id}",
        headers=[("Content-Type", "application/json"), create_admin_authorization_header()],
        data=json.dumps(data),
    )

    updated_template = Template.query.get(template.id)
    assert updated_template.archived
    assert not updated_template.folder


def test_should_be_able_to_get_all_templates_for_a_service(client, sample_user, sample_service):
    data = {
        "name": "my template 1",
        "template_type": BROADCAST_TYPE,
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data_1 = json.dumps(data)
    data = {
        "name": "my template 2",
        "template_type": BROADCAST_TYPE,
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data_2 = json.dumps(data)
    auth_header = create_admin_authorization_header()
    client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data_1,
    )
    auth_header = create_admin_authorization_header()

    client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data_2,
    )

    auth_header = create_admin_authorization_header()

    response = client.get("/service/{}/template".format(sample_service.id), headers=[auth_header])

    assert response.status_code == 200
    update_json_resp = json.loads(response.get_data(as_text=True))
    assert update_json_resp["data"][0]["name"] == "my template 1"
    assert update_json_resp["data"][0]["version"] == 1
    assert update_json_resp["data"][0]["created_at"]
    assert update_json_resp["data"][1]["name"] == "my template 2"
    assert update_json_resp["data"][1]["version"] == 1
    assert update_json_resp["data"][1]["created_at"]


def test_should_get_only_templates_for_that_service(admin_request, notify_db_session):
    service_1 = create_service(service_name="service_1")
    service_2 = create_service(service_name="service_2")
    id_1 = create_template(service_1).id
    id_2 = create_template(service_1).id
    id_3 = create_template(service_2).id

    json_resp_1 = admin_request.get("template.get_all_templates_for_service", service_id=service_1.id)
    json_resp_2 = admin_request.get("template.get_all_templates_for_service", service_id=service_2.id)

    assert {template["id"] for template in json_resp_1["data"]} == {str(id_1), str(id_2)}
    assert {template["id"] for template in json_resp_2["data"]} == {str(id_3)}


@pytest.mark.parametrize(
    "extra_args",
    (
        {},
        {"detailed": True},
        {"detailed": "True"},
    ),
)
def test_should_get_return_all_fields_by_default(
    admin_request,
    sample_service,
    extra_args,
):
    create_template(
        sample_service,
        template_type="broadcast",
        content="This is a test",
    )
    json_response = admin_request.get(
        "template.get_all_templates_for_service", service_id=sample_service.id, **extra_args
    )
    assert json_response["data"][0].keys() == {
        "archived",
        "broadcast_data",
        "content",
        "created_at",
        "created_by",
        "folder",
        "id",
        "name",
        "service",
        "template_type",
        "updated_at",
        "version",
    }


def test_should_get_a_single_template(client, sample_user, sample_service):
    template = create_template(sample_service, template_type=BROADCAST_TYPE, content="Here is some sample content")

    response = client.get(
        "/service/{}/template/{}".format(sample_service.id, template.id), headers=[create_admin_authorization_header()]
    )

    data = json.loads(response.get_data(as_text=True))["data"]

    assert response.status_code == 200
    assert data["content"] == "Here is some sample content"


def test_should_return_empty_array_if_no_templates_for_service(client, sample_service):
    auth_header = create_admin_authorization_header()

    response = client.get("/service/{}/template".format(sample_service.id), headers=[auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp["data"]) == 0


def test_should_return_404_if_no_templates_for_service_with_id(client, sample_service, fake_uuid):
    auth_header = create_admin_authorization_header()

    response = client.get("/service/{}/template/{}".format(sample_service.id, fake_uuid), headers=[auth_header])

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_create_400_for_over_limit_content(
    client,
    notify_api,
    sample_user,
    fake_uuid,
):
    sample_service = create_service(service_permissions=[BROADCAST_TYPE])
    content = "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(MAX_BROADCAST_CHAR_COUNT + 1)
    )
    data = {
        "name": "too big template",
        "template_type": BROADCAST_TYPE,
        "content": content,
        "service": str(sample_service.id),
        "created_by": str(sample_service.created_by.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert ("Content has a character count greater than the limit of {}").format(MAX_BROADCAST_CHAR_COUNT) in json_resp[
        "message"
    ]["content"]


def test_update_400_for_over_limit_content(client, notify_api, sample_user, sample_template):
    json_data = json.dumps(
        {
            "content": "".join(
                random.choice(string.ascii_uppercase + string.digits) for _ in range(MAX_BROADCAST_CHAR_COUNT + 1)
            ),
            "created_by": str(sample_user.id),
        }
    )
    auth_header = create_admin_authorization_header()
    resp = client.post(
        "/service/{}/template/{}".format(sample_template.service.id, sample_template.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=json_data,
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert ("Content has a character count greater than the limit of {}").format(MAX_BROADCAST_CHAR_COUNT) in json_resp[
        "message"
    ]["content"]


def test_should_return_all_template_versions_for_service_and_template_id(client, sample_template):
    original_content = sample_template.content
    from app.dao.templates_dao import dao_update_template

    sample_template.content = original_content + "1"
    dao_update_template(sample_template)
    sample_template.content = original_content + "2"
    dao_update_template(sample_template)

    auth_header = create_admin_authorization_header()
    resp = client.get(
        "/service/{}/template/{}/versions".format(sample_template.service_id, sample_template.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 200
    resp_json = json.loads(resp.get_data(as_text=True))["data"]
    assert len(resp_json) == 3
    for x in resp_json:
        if x["version"] == 1:
            assert x["content"] == original_content
        elif x["version"] == 2:
            assert x["content"] == original_content + "1"
        else:
            assert x["content"] == original_content + "2"


def test_update_does_not_create_new_version_when_there_is_no_change(client, sample_template):
    auth_header = create_admin_authorization_header()
    data = {
        "template_type": sample_template.template_type,
        "content": sample_template.content,
    }
    resp = client.post(
        "/service/{}/template/{}".format(sample_template.service_id, sample_template.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 200

    template = dao_get_template_by_id(sample_template.id)
    assert template.version == 1


@pytest.mark.parametrize(
    "post_data, expected_errors",
    [
        (
            {},
            [
                {"error": "ValidationError", "message": "name is a required property"},
                {"error": "ValidationError", "message": "template_type is a required property"},
                {"error": "ValidationError", "message": "content is a required property"},
                {"error": "ValidationError", "message": "service is a required property"},
                {"error": "ValidationError", "message": "created_by is a required property"},
            ],
        ),
        (
            {
                "template_type": "broadcast",
                "content": "hi",
                "service": "1af43c02-b5a8-4923-ad7f-5279b75ff2d0",
                "created_by": "30587644-9083-44d8-a114-98887f07f1e3",
            },
            [
                {
                    "error": "ValidationError",
                    "message": "name is a required property",
                },
            ],
        ),
    ],
)
def test_create_template_validates_against_json_schema(
    admin_request,
    sample_service_full_permissions,
    post_data,
    expected_errors,
):
    response = admin_request.post(
        "template.create_template", service_id=sample_service_full_permissions.id, _data=post_data, _expected_status=400
    )
    assert response["errors"] == expected_errors


def test_purge_templates_and_folders_for_service_removes_db_objects(mocker, sample_service, admin_request):
    with requests_mock.Mocker():
        template_purge_mock = mocker.patch("app.dao.templates_dao.dao_purge_templates_for_service")
        folder_purge_mock = mocker.patch("app.dao.template_folder_dao.dao_purge_template_folders_for_service")

        response = admin_request.delete(
            "template.purge_templates_and_folders_for_service",
            service_id=sample_service.id,
            _expected_status=200,
        )

        assert (
            response["message"] == f"Purged templates, archived templates and folders from service {sample_service.id}."
        )

        assert template_purge_mock.called_once_with(sample_service.id)
        assert folder_purge_mock.called_once_with(sample_service.id)
