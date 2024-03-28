import uuid
from datetime import datetime

from flask import current_app
from sqlalchemy import asc, desc

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.dao.users_dao import get_user_by_id
from app.models import (
    LETTER_TYPE,
    SECOND_CLASS,
    BroadcastMessage,
    Template,
    TemplateHistory,
    TemplateRedacted,
)


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_create_template(template):
    template.id = uuid.uuid4()  # must be set now so version history model can use same id
    template.archived = False

    redacted_dict = {
        "template": template,
        "redact_personalisation": False,
    }
    if template.created_by:
        redacted_dict.update({"updated_by": template.created_by})
    else:
        redacted_dict.update({"updated_by_id": template.created_by_id})

    template.template_redacted = TemplateRedacted(**redacted_dict)

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
            "updated_at": datetime.utcnow(),
            "version": Template.version + 1,
        }
    )
    template = Template.query.filter_by(id=template_id).one()

    history = TemplateHistory(
        **{
            "id": template.id,
            "name": template.name,
            "template_type": template.template_type,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "content": template.content,
            "service_id": template.service_id,
            "subject": template.subject,
            "postage": template.postage,
            "created_by_id": template.created_by_id,
            "version": template.version,
            "archived": template.archived,
            "process_type": template.process_type,
            "service_letter_contact_id": template.service_letter_contact_id,
            "broadcast_data": template.broadcast_data,
        }
    )
    db.session.add(history)
    return template


@autocommit
def dao_redact_template(template, user_id):
    template.template_redacted.redact_personalisation = True
    template.template_redacted.updated_at = datetime.utcnow()
    template.template_redacted.updated_by_id = user_id
    db.session.add(template.template_redacted)


def dao_get_template_by_id_and_service_id(template_id, service_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(
            id=template_id, hidden=False, service_id=service_id, version=version
        ).one()
    return Template.query.filter_by(id=template_id, hidden=False, service_id=service_id).one()


def dao_get_template_by_id(template_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(id=template_id, version=version).one()
    return Template.query.filter_by(id=template_id).one()


def dao_get_all_templates_for_service(service_id, template_type=None):
    if template_type is not None:
        return (
            Template.query.filter_by(service_id=service_id, template_type=template_type, hidden=False, archived=False)
            .order_by(
                asc(Template.name),
                asc(Template.template_type),
            )
            .all()
        )

    return (
        Template.query.filter_by(service_id=service_id, hidden=False, archived=False)
        .order_by(
            asc(Template.name),
            asc(Template.template_type),
        )
        .all()
    )


def dao_get_template_versions(service_id, template_id):
    return (
        TemplateHistory.query.filter_by(
            service_id=service_id,
            id=template_id,
            hidden=False,
        )
        .order_by(desc(TemplateHistory.version))
        .all()
    )


def get_precompiled_letter_template(service_id):
    template = Template.query.filter_by(service_id=service_id, template_type=LETTER_TYPE, hidden=True).first()
    if template is not None:
        return template

    template = Template(
        name="Pre-compiled PDF",
        created_by=get_user_by_id(current_app.config["NOTIFY_USER_ID"]),
        service_id=service_id,
        template_type=LETTER_TYPE,
        hidden=True,
        subject="Pre-compiled PDF",
        content="",
        postage=SECOND_CLASS,
    )

    dao_create_template(template)

    return template


@autocommit
def dao_purge_templates_for_service(service_id):
    templates = Template.query.filter_by(service_id=service_id).all()

    # DELETE
    # FROM template_redacted
    # WHERE template_id IN (
    #     SELECT id
    #     FROM public.templates
    #     WHERE service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    # )
    redacted_templates = TemplateRedacted.query.filter(
        TemplateRedacted.template_id.in_([x.id for x in templates])
    ).all()
    for redacted_template in redacted_templates:
        db.session.delete(redacted_template)

    # DELETE
    # FROM public.templates as t
    # WHERE service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    for template in templates:
        db.session.delete(template)
    db.session.flush()

    # DELETE
    # FROM public.template_folder_map
    # WHERE template_id IN (
    #     SELECT id as template_id
    #     FROM public.templates
    #     WHERE public.templates.service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    # )
    ids = [f"'{str(x.id)}'" for x in templates]
    ids_string = ", ".join(ids)
    query = f"DELETE FROM template_folder_map WHERE template_id IN ({ids_string})"
    db.session.execute(query)
    db.session.flush()

    # DELETE
    # FROM public.templates_history
    # WHERE id NOT IN (
    #     SELECT DISTINCT ON (template_id) template_id as id
    #     FROM public.broadcast_message
    #     WHERE service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    #         AND template_id IS NOT NULL
    # )
    messages_from_templates = BroadcastMessage.query.filter(
        BroadcastMessage.service_id == service_id, BroadcastMessage.template_id.isnot(None)
    ).distinct()
    template_histories = TemplateHistory.query.filter(
        ~TemplateHistory.id.in_([x.template_id for x in messages_from_templates])
    ).all()
    for template_history in template_histories:
        db.session.delete(template_history)
