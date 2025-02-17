from app.models import ADMIN_INVITE_USER
from tests.app.db import create_admin_action


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
