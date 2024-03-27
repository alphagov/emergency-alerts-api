from app import db
from app.dao.dao_utils import autocommit
from app.models import (
    Template,
    TemplateFolder,
    template_folder_map,
    user_folder_permissions,
)


def dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id):
    return TemplateFolder.query.filter(
        TemplateFolder.id == template_folder_id, TemplateFolder.service_id == service_id
    ).one()


def dao_get_valid_template_folders_by_id(folder_ids):
    return TemplateFolder.query.filter(TemplateFolder.id.in_(folder_ids)).all()


@autocommit
def dao_create_template_folder(template_folder):
    db.session.add(template_folder)


@autocommit
def dao_update_template_folder(template_folder):
    db.session.add(template_folder)


@autocommit
def dao_delete_template_folder(template_folder):
    db.session.delete(template_folder)


@autocommit
def dao_purge_template_folders_for_service(service_id):
    # DELETE
    # FROM public.template_folder_map
    # WHERE template_id IN (
    #     SELECT id as template_id
    #     FROM public.templates
    #     WHERE public.templates.service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    # )
    templates = Template.query.filter_by(service_id=service_id).all()
    folder_mappings = template_folder_map.query.filter(
        template_folder_map.template_id.in_([x.template_id for x in templates])
    )
    for mapping in folder_mappings:
        db.session.delete(mapping)

    # DELETE
    # FROM public.user_folder_permissions
    # WHERE service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    permissions = user_folder_permissions.query.filter(user_folder_permissions.service_id == service_id).all()
    for permission in permissions:
        db.session.delete(permission)

    # DELETE
    # FROM public.template_folder
    # WHERE service_id = '8e1d56fa-12a8-4d00-bed2-db47180bed0a'
    folders = TemplateFolder.query.filter(TemplateFolder.service_id == service_id).all()
    for folder in folders:
        db.session.delete(folder)
