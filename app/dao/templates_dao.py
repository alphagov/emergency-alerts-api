import uuid
from datetime import datetime, timezone

from sqlalchemy import asc, desc

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.models import Template, TemplateHistory


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_create_template(template):
    template.id = uuid.uuid4()  # must be set now so version history model can use same id
    template.archived = False
    db.session.add(template)


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_update_template(template):
    db.session.add(template)


@autocommit
def dao_update_template_reply_to(template_id, reply_to):
    Template.query.filter_by(id=template_id).update(
        {
            "service_letter_contact_id": reply_to,
            "updated_at": datetime.now(timezone.utc),
            "version": Template.version + 1,
        }
    )
    template = Template.query.filter_by(id=template_id).one()

    history = TemplateHistory(
        **{
            "id": template.id,
            "reference": template.reference,
            "template_type": template.template_type,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "content": template.content,
            "service_id": template.service_id,
            "created_by_id": template.created_by_id,
            "version": template.version,
            "archived": template.archived,
            "broadcast_data": template.broadcast_data,
        }
    )
    db.session.add(history)
    return template


def dao_get_template_by_id_and_service_id(template_id, service_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(id=template_id, service_id=service_id, version=version).one()
    return Template.query.filter_by(id=template_id, service_id=service_id).one()


def dao_get_template_by_id(template_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(id=template_id, version=version).one()
    return Template.query.filter_by(id=template_id).one()


def dao_get_all_templates_for_service(service_id, template_type=None):
    if template_type is not None:
        return (
            Template.query.filter_by(service_id=service_id, template_type=template_type, archived=False)
            .order_by(
                asc(Template.reference),
                asc(Template.template_type),
            )
            .all()
        )

    return (
        Template.query.filter_by(service_id=service_id, archived=False)
        .order_by(
            asc(Template.reference),
            asc(Template.template_type),
        )
        .all()
    )


def dao_get_template_versions(service_id, template_id):
    return (
        TemplateHistory.query.filter_by(
            service_id=service_id,
            id=template_id,
        )
        .order_by(desc(TemplateHistory.version))
        .all()
    )


@autocommit
def dao_purge_templates_for_service(service_id):
    templates = Template.query.filter_by(service_id=service_id).all()

    for template in templates:
        db.session.delete(template)
    db.session.flush()

    ids = [f"'{str(x.id)}'" for x in templates]
    ids_string = ", ".join(ids)
    if len(ids_string) > 0:
        query = f"DELETE FROM template_folder_map WHERE template_id IN ({ids_string})"
        db.session.execute(query)
        db.session.flush()

    template_histories = TemplateHistory.query.filter_by(service_id=service_id).all()
    for template_history in template_histories:
        db.session.delete(template_history)
