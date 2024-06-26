import json
import random
import string
import uuid
from datetime import datetime, timedelta

import pytest
import requests_mock
from emergency_alerts_utils import SMS_CHAR_COUNT_LIMIT
from freezegun import freeze_time

from app.dao.templates_dao import dao_get_template_by_id, dao_redact_template
from app.models import (
    BROADCAST_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    SMS_TYPE,
    Template,
    TemplateHistory,
)
from tests import create_admin_authorization_header
from tests.app.db import (
    create_letter_contact,
    create_service,
    create_template,
    create_template_folder,
)


@pytest.mark.parametrize(
    "template_type, subject",
    [
        (BROADCAST_TYPE, None),
        (SMS_TYPE, None),
        (EMAIL_TYPE, "subject"),
        (LETTER_TYPE, "subject"),
    ],
)
def test_should_create_a_new_template_for_a_service(client, sample_user, template_type, subject):
    service = create_service(service_permissions=[template_type])
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template <b>content</b>",
        "service": str(service.id),
        "created_by": str(sample_user.id),
    }
    if subject:
        data.update({"subject": subject})
    if template_type == LETTER_TYPE:
        data.update({"postage": "first"})
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
    assert json_resp["data"]["template_type"] == template_type
    assert json_resp["data"]["content"] == "template <b>content</b>"
    assert json_resp["data"]["service"] == str(service.id)
    assert json_resp["data"]["id"]
    assert json_resp["data"]["version"] == 1
    assert json_resp["data"]["process_type"] == "normal"
    assert json_resp["data"]["created_by"] == str(sample_user.id)
    if subject:
        assert json_resp["data"]["subject"] == "subject"
    else:
        assert not json_resp["data"]["subject"]

    if template_type == LETTER_TYPE:
        assert json_resp["data"]["postage"] == "first"
    else:
        assert not json_resp["data"]["postage"]

    template = Template.query.get(json_resp["data"]["id"])
    from app.schemas import template_schema

    assert sorted(json_resp["data"]) == sorted(template_schema.dump(template))


def test_create_a_new_template_for_a_service_adds_folder_relationship(client, sample_service):
    parent_folder = create_template_folder(service=sample_service, name="parent folder")

    data = {
        "name": "my template",
        "template_type": "sms",
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


@pytest.mark.parametrize(
    "template_type, expected_postage", [(SMS_TYPE, None), (EMAIL_TYPE, None), (LETTER_TYPE, "second")]
)
def test_create_a_new_template_for_a_service_adds_postage_for_letters_only(
    client, sample_service, template_type, expected_postage
):
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template <b>content</b>",
        "service": str(sample_service.id),
        "created_by": str(sample_service.users[0].id),
    }
    if template_type in [EMAIL_TYPE, LETTER_TYPE]:
        data["subject"] = "Hi, I have good news"

    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    template = Template.query.filter(Template.name == "my template").first()
    assert template.postage == expected_postage


def test_create_template_should_return_400_if_folder_is_for_a_different_service(client, sample_service):
    service2 = create_service(service_name="second service")
    parent_folder = create_template_folder(service=service2)

    data = {
        "name": "my template",
        "template_type": "sms",
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
        "template_type": "sms",
        "content": "template <b>content</b>",
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
        "template_type": SMS_TYPE,
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
    "permissions, template_type, subject, expected_error",
    [
        (
            [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE],
            BROADCAST_TYPE,
            None,
            {"template_type": ["Creating broadcast message templates is not allowed"]},
        ),  # noqa
        ([EMAIL_TYPE], SMS_TYPE, None, {"template_type": ["Creating text message templates is not allowed"]}),
        ([SMS_TYPE], EMAIL_TYPE, "subject", {"template_type": ["Creating email templates is not allowed"]}),
        ([SMS_TYPE], LETTER_TYPE, "subject", {"template_type": ["Creating letter templates is not allowed"]}),
    ],
)
def test_should_raise_error_on_create_if_no_permission(
    client, sample_user, permissions, template_type, subject, expected_error
):
    service = create_service(service_permissions=permissions)
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template content",
        "service": str(service.id),
        "created_by": str(sample_user.id),
    }
    if subject:
        data.update({"subject": subject})

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
        (SMS_TYPE, [EMAIL_TYPE], {"template_type": ["Updating text message templates is not allowed"]}),
        (EMAIL_TYPE, [LETTER_TYPE], {"template_type": ["Updating email templates is not allowed"]}),
        (LETTER_TYPE, [SMS_TYPE], {"template_type": ["Updating letter templates is not allowed"]}),
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
    data = {"name": "my template", "template_type": SMS_TYPE, "content": "template content", "service": service_id}
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


@pytest.mark.parametrize("template_type", [EMAIL_TYPE, LETTER_TYPE])
def test_must_have_a_subject_on_an_email_or_letter_template(client, sample_user, sample_service, template_type):
    data = {
        "name": "my template",
        "template_type": template_type,
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    response = client.post(
        "/service/{}/template".format(sample_service.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["errors"][0]["error"] == "ValidationError"
    assert json_resp["errors"][0]["message"] == "subject is a required property"


def test_update_should_update_a_template(client, sample_user):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service, template_type="letter", postage="second")

    assert template.created_by == service.created_by
    assert template.created_by != sample_user

    data = {"content": "my template has new content, swell!", "created_by": str(sample_user.id), "postage": "first"}
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()

    update_response = client.post(
        "/service/{}/template/{}".format(service.id, template.id),
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )

    assert update_response.status_code == 200
    update_json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_json_resp["data"]["content"] == ("my template has new content, swell!")
    assert update_json_resp["data"]["postage"] == "first"
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


def test_get_precompiled_template_for_service(
    client,
    notify_user,
    sample_service,
):
    assert len(sample_service.templates) == 0

    response = client.get(
        "/service/{}/template/precompiled".format(sample_service.id),
        headers=[create_admin_authorization_header()],
    )
    assert response.status_code == 200
    assert len(sample_service.templates) == 1

    data = json.loads(response.get_data(as_text=True))
    assert data["name"] == "Pre-compiled PDF"
    assert data["hidden"] is True


def test_get_precompiled_template_for_service_when_service_has_existing_precompiled_template(
    client,
    notify_user,
    sample_service,
):
    create_template(
        sample_service, template_name="Exisiting precompiled template", template_type=LETTER_TYPE, hidden=True
    )
    assert len(sample_service.templates) == 1

    response = client.get(
        "/service/{}/template/precompiled".format(sample_service.id),
        headers=[create_admin_authorization_header()],
    )

    assert response.status_code == 200
    assert len(sample_service.templates) == 1

    data = json.loads(response.get_data(as_text=True))
    assert data["name"] == "Exisiting precompiled template"
    assert data["hidden"] is True


def test_should_be_able_to_get_all_templates_for_a_service(client, sample_user, sample_service):
    data = {
        "name": "my template 1",
        "template_type": EMAIL_TYPE,
        "subject": "subject 1",
        "content": "template content",
        "service": str(sample_service.id),
        "created_by": str(sample_user.id),
    }
    data_1 = json.dumps(data)
    data = {
        "name": "my template 2",
        "template_type": EMAIL_TYPE,
        "subject": "subject 2",
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
    sample_email_template,
    extra_args,
):
    json_response = admin_request.get(
        "template.get_all_templates_for_service", service_id=sample_email_template.service.id, **extra_args
    )
    assert json_response["data"][0].keys() == {
        "archived",
        "broadcast_data",
        "content",
        "created_at",
        "created_by",
        "folder",
        "hidden",
        "id",
        "name",
        "postage",
        "process_type",
        "redact_personalisation",
        "reply_to",
        "reply_to_text",
        "service",
        "service_letter_contact",
        "subject",
        "template_redacted",
        "template_type",
        "updated_at",
        "version",
    }


@pytest.mark.parametrize(
    "extra_args",
    (
        {"detailed": False},
        {"detailed": "False"},
    ),
)
@pytest.mark.parametrize(
    "template_type, expected_content",
    (
        (EMAIL_TYPE, None),
        (SMS_TYPE, None),
        (LETTER_TYPE, None),
        (BROADCAST_TYPE, "This is a test"),
    ),
)
def test_should_not_return_content_and_subject_if_requested(
    admin_request,
    sample_service,
    extra_args,
    template_type,
    expected_content,
):
    create_template(
        sample_service,
        template_type=template_type,
        content="This is a test",
    )
    json_response = admin_request.get(
        "template.get_all_templates_for_service", service_id=sample_service.id, **extra_args
    )
    assert json_response["data"][0].keys() == {
        "content",
        "folder",
        "id",
        "name",
        "template_type",
    }
    assert json_response["data"][0]["content"] == expected_content


@pytest.mark.parametrize(
    "subject, content, template_type",
    [
        ("about your ((thing))", "hello ((name)) we’ve received your ((thing))", EMAIL_TYPE),
        (None, "hello ((name)) we’ve received your ((thing))", SMS_TYPE),
        ("about your ((thing))", "hello ((name)) we’ve received your ((thing))", LETTER_TYPE),
    ],
)
def test_should_get_a_single_template(client, sample_user, sample_service, subject, content, template_type):
    template = create_template(sample_service, template_type=template_type, subject=subject, content=content)

    response = client.get(
        "/service/{}/template/{}".format(sample_service.id, template.id), headers=[create_admin_authorization_header()]
    )

    data = json.loads(response.get_data(as_text=True))["data"]

    assert response.status_code == 200
    assert data["content"] == content
    assert data["subject"] == subject
    assert data["process_type"] == "normal"
    assert not data["redact_personalisation"]


@pytest.mark.parametrize(
    "subject, content, path, expected_subject, expected_content, expected_error",
    [
        (
            "about your thing",
            "hello user we’ve received your thing",
            "/service/{}/template/{}/preview",
            "about your thing",
            "hello user we’ve received your thing",
            None,
        ),
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            "/service/{}/template/{}/preview?name=Amala&thing=document",
            "about your document",
            "hello Amala we’ve received your document",
            None,
        ),
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            "/service/{}/template/{}/preview?eman=Amala&gniht=document",
            None,
            None,
            "Missing personalisation: thing, name",
        ),
        (
            "about your ((thing))",
            "hello ((name)) we’ve received your ((thing))",
            "/service/{}/template/{}/preview?name=Amala&thing=document&foo=bar",
            "about your document",
            "hello Amala we’ve received your document",
            None,
        ),
    ],
)
def test_should_preview_a_single_template(
    client, sample_service, subject, content, path, expected_subject, expected_content, expected_error
):
    template = create_template(sample_service, template_type=EMAIL_TYPE, subject=subject, content=content)

    response = client.get(path.format(sample_service.id, template.id), headers=[create_admin_authorization_header()])

    content = json.loads(response.get_data(as_text=True))

    if expected_error:
        assert response.status_code == 400
        assert content["message"]["template"] == [expected_error]
    else:
        assert response.status_code == 200
        assert content["content"] == expected_content
        assert content["subject"] == expected_subject


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


@pytest.mark.parametrize(
    "template_type",
    (
        SMS_TYPE,
        BROADCAST_TYPE,
    ),
)
def test_create_400_for_over_limit_content(
    client,
    notify_api,
    sample_user,
    fake_uuid,
    template_type,
):
    sample_service = create_service(service_permissions=[template_type])
    content = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(SMS_CHAR_COUNT_LIMIT + 1))
    data = {
        "name": "too big template",
        "template_type": template_type,
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
    assert ("Content has a character count greater than the limit of {}").format(SMS_CHAR_COUNT_LIMIT) in json_resp[
        "message"
    ]["content"]


def test_update_400_for_over_limit_content(client, notify_api, sample_user, sample_template):
    json_data = json.dumps(
        {
            "content": "".join(
                random.choice(string.ascii_uppercase + string.digits) for _ in range(SMS_CHAR_COUNT_LIMIT + 1)
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
    assert ("Content has a character count greater than the limit of {}").format(SMS_CHAR_COUNT_LIMIT) in json_resp[
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


def test_update_set_process_type_on_template(client, sample_template):
    auth_header = create_admin_authorization_header()
    data = {"process_type": "priority"}
    resp = client.post(
        "/service/{}/template/{}".format(sample_template.service_id, sample_template.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 200

    template = dao_get_template_by_id(sample_template.id)
    assert template.process_type == "priority"


def test_create_a_template_with_reply_to(admin_request, sample_user):
    service = create_service(service_permissions=["letter"])
    letter_contact = create_letter_contact(service, "Edinburgh, ED1 1AA")
    data = {
        "name": "my template",
        "subject": "subject",
        "template_type": "letter",
        "content": "template <b>content</b>",
        "service": str(service.id),
        "created_by": str(sample_user.id),
        "reply_to": str(letter_contact.id),
    }

    json_resp = admin_request.post("template.create_template", service_id=service.id, _data=data, _expected_status=201)

    assert json_resp["data"]["template_type"] == "letter"
    assert json_resp["data"]["reply_to"] == str(letter_contact.id)
    assert json_resp["data"]["reply_to_text"] == letter_contact.contact_block

    template = Template.query.get(json_resp["data"]["id"])
    from app.schemas import template_schema

    assert sorted(json_resp["data"]) == sorted(template_schema.dump(template))
    th = TemplateHistory.query.filter_by(id=template.id, version=1).one()
    assert th.service_letter_contact_id == letter_contact.id


def test_create_a_template_with_foreign_service_reply_to(admin_request, sample_user):
    service = create_service(service_permissions=["letter"])
    service2 = create_service(
        service_name="test service", email_from="test@example.com", service_permissions=["letter"]
    )
    letter_contact = create_letter_contact(service2, "Edinburgh, ED1 1AA")
    data = {
        "name": "my template",
        "subject": "subject",
        "template_type": "letter",
        "content": "template <b>content</b>",
        "service": str(service.id),
        "created_by": str(sample_user.id),
        "reply_to": str(letter_contact.id),
    }

    json_resp = admin_request.post("template.create_template", service_id=service.id, _data=data, _expected_status=400)

    assert json_resp["message"] == "letter_contact_id {} does not exist in database for service id {}".format(
        str(letter_contact.id), str(service.id)
    )


@pytest.mark.parametrize(
    "post_data, expected_errors",
    [
        (
            {},
            [
                {"error": "ValidationError", "message": "subject is a required property"},
                {"error": "ValidationError", "message": "name is a required property"},
                {"error": "ValidationError", "message": "template_type is a required property"},
                {"error": "ValidationError", "message": "content is a required property"},
                {"error": "ValidationError", "message": "service is a required property"},
                {"error": "ValidationError", "message": "created_by is a required property"},
            ],
        ),
        (
            {
                "name": "my template",
                "template_type": "sms",
                "content": "hi",
                "postage": "third",
                "service": "1af43c02-b5a8-4923-ad7f-5279b75ff2d0",
                "created_by": "30587644-9083-44d8-a114-98887f07f1e3",
            },
            [
                {
                    "error": "ValidationError",
                    "message": "postage invalid. It must be first, second, europe or rest-of-world.",
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


@pytest.mark.parametrize(
    "template_default, service_default",
    [("template address", "service address"), (None, "service address"), ("template address", None), (None, None)],
)
def test_get_template_reply_to(client, sample_service, template_default, service_default):
    auth_header = create_admin_authorization_header()
    if service_default:
        create_letter_contact(service=sample_service, contact_block=service_default, is_default=True)
    if template_default:
        template_default_contact = create_letter_contact(
            service=sample_service, contact_block=template_default, is_default=False
        )
    reply_to_id = str(template_default_contact.id) if template_default else None
    template = create_template(service=sample_service, template_type="letter", reply_to=reply_to_id)

    resp = client.get("/service/{}/template/{}".format(template.service_id, template.id), headers=[auth_header])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    json_resp = json.loads(resp.get_data(as_text=True))

    assert "service_letter_contact_id" not in json_resp["data"]
    assert json_resp["data"]["reply_to"] == reply_to_id
    assert json_resp["data"]["reply_to_text"] == template_default


def test_update_template_reply_to(client, sample_letter_template):
    auth_header = create_admin_authorization_header()
    letter_contact = create_letter_contact(sample_letter_template.service, "Edinburgh, ED1 1AA")
    data = {
        "reply_to": str(letter_contact.id),
    }

    resp = client.post(
        "/service/{}/template/{}".format(sample_letter_template.service_id, sample_letter_template.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)

    template = dao_get_template_by_id(sample_letter_template.id)
    assert template.service_letter_contact_id == letter_contact.id
    th = TemplateHistory.query.filter_by(id=sample_letter_template.id, version=2).one()
    assert th.service_letter_contact_id == letter_contact.id


def test_update_template_reply_to_set_to_blank(client, notify_db_session):
    auth_header = create_admin_authorization_header()
    service = create_service(service_permissions=["letter"])
    letter_contact = create_letter_contact(service, "Edinburgh, ED1 1AA")
    template = create_template(service=service, template_type="letter", reply_to=letter_contact.id)

    data = {
        "reply_to": None,
    }

    resp = client.post(
        "/service/{}/template/{}".format(template.service_id, template.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)

    template = dao_get_template_by_id(template.id)
    assert template.service_letter_contact_id is None
    th = TemplateHistory.query.filter_by(id=template.id, version=2).one()
    assert th.service_letter_contact_id is None


def test_update_template_validates_postage(admin_request, sample_service_full_permissions):
    template = create_template(service=sample_service_full_permissions, template_type="letter")

    response = admin_request.post(
        "template.update_template",
        service_id=sample_service_full_permissions.id,
        template_id=template.id,
        _data={"postage": "third"},
        _expected_status=400,
    )
    assert "postage invalid" in response["errors"][0]["message"]


def test_update_template_with_foreign_service_reply_to(client, sample_letter_template):
    auth_header = create_admin_authorization_header()

    service2 = create_service(
        service_name="test service", email_from="test@example.com", service_permissions=["letter"]
    )
    letter_contact = create_letter_contact(service2, "Edinburgh, ED1 1AA")

    data = {
        "reply_to": str(letter_contact.id),
    }

    resp = client.post(
        "/service/{}/template/{}".format(sample_letter_template.service_id, sample_letter_template.id),
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert resp.status_code == 400, resp.get_data(as_text=True)
    json_resp = json.loads(resp.get_data(as_text=True))

    assert json_resp["message"] == "letter_contact_id {} does not exist in database for service id {}".format(
        str(letter_contact.id), str(sample_letter_template.service_id)
    )


def test_update_redact_template(admin_request, sample_template):
    assert sample_template.redact_personalisation is False

    data = {"redact_personalisation": True, "created_by": str(sample_template.created_by_id)}

    dt = datetime.now()

    with freeze_time(dt):
        resp = admin_request.post(
            "template.update_template",
            service_id=sample_template.service_id,
            template_id=sample_template.id,
            _data=data,
        )

    assert resp is None

    assert sample_template.redact_personalisation is True
    assert sample_template.template_redacted.updated_by_id == sample_template.created_by_id
    assert sample_template.template_redacted.updated_at == dt

    assert sample_template.version == 1


def test_update_redact_template_ignores_other_properties(admin_request, sample_template):
    data = {"name": "Foo", "redact_personalisation": True, "created_by": str(sample_template.created_by_id)}

    admin_request.post(
        "template.update_template", service_id=sample_template.service_id, template_id=sample_template.id, _data=data
    )

    assert sample_template.redact_personalisation is True
    assert sample_template.name != "Foo"


def test_update_redact_template_does_nothing_if_already_redacted(admin_request, sample_template):
    dt = datetime.now()
    with freeze_time(dt):
        dao_redact_template(sample_template, sample_template.created_by_id)

    data = {"redact_personalisation": True, "created_by": str(sample_template.created_by_id)}

    with freeze_time(dt + timedelta(days=1)):
        resp = admin_request.post(
            "template.update_template",
            service_id=sample_template.service_id,
            template_id=sample_template.id,
            _data=data,
        )

    assert resp is None

    assert sample_template.redact_personalisation is True
    # make sure that it hasn't been updated
    assert sample_template.template_redacted.updated_at == dt


def test_update_redact_template_400s_if_no_created_by(admin_request, sample_template):
    original_updated_time = sample_template.template_redacted.updated_at
    resp = admin_request.post(
        "template.update_template",
        service_id=sample_template.service_id,
        template_id=sample_template.id,
        _data={"redact_personalisation": True},
        _expected_status=400,
    )

    assert resp == {"result": "error", "message": {"created_by": ["Field is required"]}}

    assert sample_template.redact_personalisation is False
    assert sample_template.template_redacted.updated_at == original_updated_time


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
