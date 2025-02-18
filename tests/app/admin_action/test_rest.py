import uuid

import pytest

from app.models import ADMIN_INVITE_USER, ADMIN_STATUS_PENDING, AdminAction
from tests.app.db import create_admin_action


def test_create_admin_action(admin_request, service_factory, sample_user, notify_db_session):
    service = service_factory.get("test")

    action_data = {
        "email_address": "pending@test.com",
        "permissions": ["create_broadcasts"],
        "login_authentication": "email_auth",
        "folder_permissions": [str(uuid.uuid4())],
    }

    action = {
        "service_id": str(service.id),
        "action_type": ADMIN_INVITE_USER,
        "action_data": action_data,
        "created_by": str(sample_user.id),
    }

    admin_request.post("admin_action.create_admin_action", action, _expected_status=201)

    actions = AdminAction.query.all()
    assert len(actions) == 1
    assert actions[0].service_id == service.id
    assert actions[0].action_type == ADMIN_INVITE_USER
    assert actions[0].action_data == action_data
    assert actions[0].created_by_id == sample_user.id
    assert actions[0].created_at is not None
    assert actions[0].status == ADMIN_STATUS_PENDING
    assert actions[0].reviewed_by is None
    assert actions[0].reviewed_at is None


def test_get_all_pending_admin_actions(admin_request, service_factory, sample_user, notify_db_session):
    service = service_factory.get("test")
    create_admin_action(service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "pending@test.com"}, "pending")
    create_admin_action(
        service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "approved@test.com"}, "approved"
    )
    create_admin_action(
        service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "rejected@test.com"}, "rejected"
    )

    response = admin_request.get("admin_action.get_pending_admin_actions", _expected_status=200)

    assert set(response.keys()) == {
        "pending",
        "services",
        "users",
    }

    pending = response["pending"]

    assert len(pending) == 1
    assert set(pending[0].keys()) == {
        "id",
        "service_id",
        "action_type",
        "action_data",
        "created_by",
        "created_at",
        "status",
        "reviewed_by",
        "reviewed_at",
    }
    assert pending[0]["service_id"] == str(service.id)
    assert pending[0]["action_type"] == "invite_user"
    assert pending[0]["action_data"] == {"email_address": "pending@test.com"}
    assert pending[0]["created_by"] == str(sample_user.id)
    assert pending[0]["created_at"] is not None
    assert pending[0]["reviewed_by"] is None
    assert pending[0]["reviewed_at"] is None

    services = response["services"]
    assert len(services) == 1
    assert services[str(service.id)]["id"] == str(service.id)
    assert services[str(service.id)]["name"] == str(service.name)
    assert services[str(service.id)]["restricted"] == service.restricted

    users = response["users"]
    assert len(users) == 1
    assert users[str(sample_user.id)]["id"] == str(sample_user.id)
    assert users[str(sample_user.id)]["name"] == str(sample_user.name)
    assert users[str(sample_user.id)]["email_address"] == str(sample_user.email_address)


def test_get_admin_action_by_id(admin_request, service_factory, sample_user, notify_db_session):
    service = service_factory.get("test")
    action = create_admin_action(
        service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "pending@test.com"}, "pending"
    )

    response = admin_request.get("admin_action.get_admin_action_by_id", action_id=str(action.id))

    assert response["id"] == str(action.id)
    assert response["created_at"] is not None
    assert response["created_by"] == str(sample_user.id)
    assert response["action_type"] == ADMIN_INVITE_USER
    assert "email_address" in response["action_data"]
    assert response["status"] == ADMIN_STATUS_PENDING


@pytest.mark.parametrize("status, expected_response_code", (("pending", 200), ("approved", 400), ("rejected", 400)))
def test_only_pending_can_be_reviewed(
    status, expected_response_code, admin_request, service_factory, sample_user, notify_db_session
):
    service = service_factory.get("test")
    action = create_admin_action(
        service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "test@test.com"}, status
    )

    review = {"status": "approved", "reviewed_by": str(sample_user.id)}

    admin_request.post(
        "admin_action.review_admin_action", review, action_id=str(action.id), _expected_status=expected_response_code
    )
