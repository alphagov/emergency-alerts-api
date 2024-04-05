from app import db
from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import (
    dao_delete_template_folder,
    dao_get_template_folder_by_id_and_service_id,
    dao_get_valid_template_folders_by_id,
    dao_purge_template_folders_for_service,
    dao_update_template_folder,
)
from app.models import user_folder_permissions
from tests.app.db import create_template_folder


def test_dao_delete_template_folder_deletes_user_folder_permissions(sample_user, sample_service):
    folder = create_template_folder(sample_service)
    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    folder.users = [service_user]

    dao_update_template_folder(folder)
    assert len(db.session.query(user_folder_permissions).all()) > 0

    dao_delete_template_folder(folder)
    assert db.session.query(user_folder_permissions).all() == []


def test_purge_template_folders_for_service(sample_user, sample_service):
    service_user = dao_get_service_user(sample_user.id, sample_service.id)

    folder_1 = create_template_folder(sample_service, name="folder_1", users=[service_user])
    folder_2 = create_template_folder(sample_service, name="folder_2", users=[service_user])

    assert dao_get_template_folder_by_id_and_service_id(folder_1.id, sample_service.id).name == "folder_1"
    assert dao_get_template_folder_by_id_and_service_id(folder_2.id, sample_service.id).name == "folder_2"

    assert len(db.session.query(user_folder_permissions).all()) > 0

    dao_purge_template_folders_for_service(sample_service.id)

    assert dao_get_valid_template_folders_by_id([folder_1.id, folder_2.id]) == []
    assert db.session.query(user_folder_permissions).all() == []
