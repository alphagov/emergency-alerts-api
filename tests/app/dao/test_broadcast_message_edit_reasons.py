import uuid

from app.dao.broadcast_message_edit_reasons import (
    dao_create_broadcast_message_edit_reason,
    dao_get_broadcast_message_edit_reasons,
    dao_get_latest_broadcast_message_edit_reason_by_broadcast_message_id_and_service_id,
)
from app.models import BROADCAST_TYPE
from tests.app.db import (
    create_broadcast_message,
    create_broadcast_message_edit_reason,
    create_template,
)


def test_get_broadcast_message_edit_reasons(notify_db_session, sample_service, sample_user, sample_user_2):
    id = uuid.uuid4()
    edit_reason_1 = create_broadcast_message_edit_reason(
        id, sample_service.id, "TEST", sample_user.id, sample_user_2.id
    )
    edit_reason_2 = create_broadcast_message_edit_reason(
        id, sample_service.id, "TEST", sample_user.id, sample_user_2.id
    )
    broadcast_message_edit_reasons = dao_get_broadcast_message_edit_reasons(
        service_id=sample_service.id, broadcast_message_id=id
    )
    assert len(broadcast_message_edit_reasons) == 2
    assert broadcast_message_edit_reasons == [
        (edit_reason_1, "Test User", "Test User 2"),
        (edit_reason_2, "Test User", "Test User 2"),
    ]


def test_get_latest_broadcast_message_edit_reason_by_id_and_service_id(
    notify_db_session, sample_service, sample_user, sample_user_2
):
    id = uuid.uuid4()
    create_broadcast_message_edit_reason(id, sample_service.id, "TEST", sample_user.id, sample_user_2.id)
    edit_reason = create_broadcast_message_edit_reason(
        id, sample_service.id, "TEST 2", sample_user.id, sample_user_2.id
    )
    latest_broadcast_message_version = (
        dao_get_latest_broadcast_message_edit_reason_by_broadcast_message_id_and_service_id(
            service_id=sample_service.id, broadcast_message_id=id
        )
    )
    assert latest_broadcast_message_version == edit_reason
    assert latest_broadcast_message_version.edit_reason == edit_reason.edit_reason


def test_create_broadcast_message_edit_reason(notify_db_session, sample_service, sample_user, sample_user_2):
    t = create_template(sample_service, BROADCAST_TYPE, template_name="Test Template Name")

    bm = create_broadcast_message(t, submitted_by=sample_user_2)
    edit_reason = dao_create_broadcast_message_edit_reason(bm, sample_service.id, sample_user.id, edit_reason="TEST")

    edit_reasons = dao_get_broadcast_message_edit_reasons(service_id=str(sample_service.id), broadcast_message_id=bm.id)
    assert edit_reasons == [(edit_reason, sample_user.name, sample_user_2.name)]
