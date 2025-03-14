import pytest
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.service_user_dao import dao_get_service_user
from app.dao.templates_dao import (
    dao_create_template,
    dao_get_all_templates_for_service,
    dao_get_template_by_id_and_service_id,
    dao_get_template_versions,
    dao_purge_templates_for_service,
    dao_update_template,
)
from app.models import Template, TemplateHistory, template_folder_map
from tests.app.db import create_template, create_template_folder


def test_create_template(sample_service, sample_user):
    data = {
        "name": "Sample Template",
        "template_type": "broadcast",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)

    assert Template.query.count() == 1
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 1
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "Sample Template"


def test_update_template(sample_service, sample_user):
    data = {
        "name": "Sample Template",
        "template_type": "broadcast",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)
    created = dao_get_all_templates_for_service(sample_service.id)[0]
    assert created.name == "Sample Template"

    created.name = "new name"
    dao_update_template(created)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "new name"


def test_get_all_templates_for_service(service_factory):
    service_1 = service_factory.get("service 1")
    service_2 = service_factory.get("service 2")

    assert Template.query.count() == 2
    assert len(dao_get_all_templates_for_service(service_1.id)) == 1
    assert len(dao_get_all_templates_for_service(service_2.id)) == 1

    create_template(
        service=service_1,
        template_name="Sample Template 1",
        template_type="broadcast",
        content="Template content",
    )
    create_template(
        service=service_1,
        template_name="Sample Template 2",
        template_type="broadcast",
        content="Template content",
    )
    create_template(
        service=service_2,
        template_name="Sample Template 3",
        template_type="broadcast",
        content="Template content",
    )

    assert Template.query.count() == 5
    assert len(dao_get_all_templates_for_service(service_1.id)) == 3
    assert len(dao_get_all_templates_for_service(service_2.id)) == 2


def test_get_all_templates_for_service_is_alphabetised(sample_service):
    create_template(
        template_name="Sample Template 1", template_type="broadcast", content="Template content", service=sample_service
    )
    template_2 = create_template(
        template_name="Sample Template 2", template_type="broadcast", content="Template content", service=sample_service
    )
    create_template(
        template_name="Sample Template 3", template_type="broadcast", content="Template content", service=sample_service
    )

    assert Template.query.count() == 3
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "Sample Template 1"
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == "Sample Template 2"
    assert dao_get_all_templates_for_service(sample_service.id)[2].name == "Sample Template 3"

    template_2.name = "AAAAA Sample Template 2"
    dao_update_template(template_2)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "AAAAA Sample Template 2"
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == "Sample Template 1"


def test_get_all_returns_empty_list_if_no_templates(sample_service):
    assert Template.query.count() == 0
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 0


def test_get_all_templates_ignores_archived_templates(sample_service):
    normal_template = create_template(template_name="Normal Template", service=sample_service, archived=False)
    archived_template = create_template(template_name="Archived Template", service=sample_service)
    # sample_template fixture uses dao, which forces archived = False at creation.
    archived_template.archived = True
    dao_update_template(archived_template)

    templates = dao_get_all_templates_for_service(sample_service.id)

    assert len(templates) == 1
    assert templates[0] == normal_template


def test_get_template_by_id_and_service(sample_service):
    sample_template = create_template(template_name="Test Template", service=sample_service)
    template = dao_get_template_by_id_and_service_id(template_id=sample_template.id, service_id=sample_service.id)
    assert template.id == sample_template.id
    assert template.name == "Test Template"
    assert template.version == sample_template.version


def test_get_template_by_id_and_service_returns_none_if_no_template(sample_service, fake_uuid):
    with pytest.raises(NoResultFound) as e:
        dao_get_template_by_id_and_service_id(template_id=fake_uuid, service_id=sample_service.id)
    assert "No row was found when one was required" in str(e.value)


def test_create_template_creates_a_history_record_with_current_data(sample_service, sample_user):
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    data = {
        "name": "Sample Template",
        "template_type": "broadcast",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)

    assert Template.query.count() == 1

    template_from_db = Template.query.first()
    template_history = TemplateHistory.query.first()

    assert template_from_db.id == template_history.id
    assert template_from_db.name == template_history.name
    assert template_from_db.version == 1
    assert template_from_db.version == template_history.version
    assert sample_user.id == template_history.created_by_id
    assert template_from_db.created_by.id == template_history.created_by_id


def test_update_template_creates_a_history_record_with_current_data(sample_service, sample_user):
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    data = {
        "name": "Sample Template",
        "template_type": "broadcast",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)

    created = dao_get_all_templates_for_service(sample_service.id)[0]
    assert created.name == "Sample Template"
    assert Template.query.count() == 1
    assert Template.query.first().version == 1
    assert TemplateHistory.query.count() == 1

    created.name = "new name"
    dao_update_template(created)

    assert Template.query.count() == 1
    assert TemplateHistory.query.count() == 2

    template_from_db = Template.query.first()

    assert template_from_db.version == 2

    assert TemplateHistory.query.filter_by(name="Sample Template").one().version == 1
    assert TemplateHistory.query.filter_by(name="new name").one().version == 2


def test_get_template_history_version(sample_user, sample_service, sample_template):
    old_content = sample_template.content
    sample_template.content = "New content"
    dao_update_template(sample_template)
    old_template = dao_get_template_by_id_and_service_id(sample_template.id, sample_service.id, "1")
    assert old_template.content == old_content


def test_get_template_versions(sample_template):
    original_content = sample_template.content
    sample_template.content = "new version"
    dao_update_template(sample_template)
    versions = dao_get_template_versions(service_id=sample_template.service_id, template_id=sample_template.id)
    assert len(versions) == 2
    versions = sorted(versions, key=lambda x: x.version)
    assert versions[0].content == original_content
    assert versions[1].content == "new version"

    assert versions[0].created_at == versions[1].created_at

    assert versions[0].updated_at is None
    assert versions[1].updated_at is not None

    from app.schemas import template_history_schema

    v = template_history_schema.dump(versions, many=True)
    assert len(v) == 2
    assert {template_history["version"] for template_history in v} == {1, 2}


def test_purge_templates_for_service(sample_user, sample_service):
    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    folder_1 = create_template_folder(sample_service, name="folder_1", users=[service_user])

    data = {
        "name": "Sample Template 1",
        "template_type": "broadcast",
        "content": "Alert template content",
        "service": sample_service,
        "created_by": sample_user,
        "folder": folder_1,
    }
    template = Template(**data)
    dao_create_template(template)

    data = {
        "name": "Sample Template 2",
        "template_type": "broadcast",
        "content": "Alert template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    folder_1 = create_template_folder(sample_service, name="folder_1", users=[service_user])

    assert Template.query.count() == 2
    assert db.session.query(template_folder_map).count() == 1
    assert TemplateHistory.query.count() == 2
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 2

    dao_purge_templates_for_service(sample_service.id)

    assert Template.query.count() == 0
    assert db.session.query(template_folder_map).count() == 0
    assert TemplateHistory.query.count() == 0
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 0
