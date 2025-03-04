import uuid

from app.dao.broadcast_message_history_dao import (
    dao_create_broadcast_message_version,
    dao_get_broadcast_message_versions,
    dao_get_latest_broadcast_message_version_by_id_and_service_id,
)
from app.models import BROADCAST_TYPE
from tests.app.db import (
    create_broadcast_message,
    create_broadcast_message_version,
    create_template,
)


def test_get_broadcast_message_versions(notify_db_session, sample_service, sample_user):
    id = uuid.uuid4()
    bmv1 = create_broadcast_message_version(service_id=sample_service.id, id=id, version=1)
    bmv2 = create_broadcast_message_version(
        service_id=sample_service.id, id=id, version=2, created_by_id=sample_user.id
    )
    broadcast_message_versions = dao_get_broadcast_message_versions(
        service_id=sample_service.id, broadcast_message_id=id
    )
    assert len(broadcast_message_versions) == 2
    assert broadcast_message_versions == [(bmv2, "Test User"), (bmv1, None)]


def test_get_latest_broadcast_message_version_by_id_and_service_id(notify_db_session, sample_service, sample_user):
    id = uuid.uuid4()
    create_broadcast_message_version(service_id=sample_service.id, id=id, version=1)
    bmv2 = create_broadcast_message_version(
        service_id=sample_service.id, id=id, version=2, created_by_id=sample_user.id
    )
    latest_broadcast_message_version = dao_get_latest_broadcast_message_version_by_id_and_service_id(
        service_id=sample_service.id, broadcast_message_id=id
    )
    assert latest_broadcast_message_version == bmv2


def test_create_broadcast_message_version(notify_db_session, sample_service, sample_user):
    t = create_template(sample_service, BROADCAST_TYPE, template_name="Test Template Name")

    bm = create_broadcast_message(t)
    dao_create_broadcast_message_version(bm, sample_service.id, sample_user.id)

    broadcast_message_versions = dao_get_broadcast_message_versions(
        service_id=str(sample_service.id), broadcast_message_id=bm.id
    )
    assert broadcast_message_versions[0][1] == "Test User"
    broadcast_message_version = broadcast_message_versions[0][0]
    assert str(broadcast_message_version.id) == str(bm.id)
    assert broadcast_message_version.reference == bm.reference
