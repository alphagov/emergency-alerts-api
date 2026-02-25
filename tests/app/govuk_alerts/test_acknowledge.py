from datetime import datetime

from flask import current_app

from app.dao.broadcast_message_dao import (
    dao_get_all_finished_broadcast_messages_with_outstanding_actions,
)
from app.models import BROADCAST_TYPE, BroadcastStatusType
from tests import create_internal_authorization_header
from tests.app.db import create_broadcast_message, create_template


def test_get_all_broadcasts_returns_list_of_broadcasts_and_200(client, sample_broadcast_service):
    template_1 = create_template(sample_broadcast_service, BROADCAST_TYPE)

    create_broadcast_message(
        template_1,
        starts_at=datetime(2021, 6, 15, 12, 0, 0),
        status=BroadcastStatusType.COMPLETED,
        finished_govuk_acknowledged=True,
    )

    create_broadcast_message(
        template_1,
        starts_at=datetime(2021, 6, 22, 12, 0, 0),
        status=BroadcastStatusType.COMPLETED,
        finished_govuk_acknowledged=False,
    )

    pending = dao_get_all_finished_broadcast_messages_with_outstanding_actions()
    assert len(pending) == 1

    jwt_client_id = current_app.config["GOVUK_ALERTS_CLIENT_ID"]
    header = create_internal_authorization_header(jwt_client_id)

    client.post("/govuk-alerts/acknowledge", headers=[header])

    new_pending = dao_get_all_finished_broadcast_messages_with_outstanding_actions()
    assert len(new_pending) == 0
