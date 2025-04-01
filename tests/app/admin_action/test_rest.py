import uuid

import pytest
from emergency_alerts_utils.admin_action import (
    ADMIN_ELEVATE_USER,
    ADMIN_INVITE_USER,
    ADMIN_STATUS_PENDING,
)

from app.models import AdminAction
from tests.app.db import create_admin_action


def test_create_admin_action(admin_request, sample_service, sample_user):
    action_data = {
        "email_address": "pending@test.com",
        "permissions": ["create_broadcasts"],
        "login_authentication": "email_auth",
        "folder_permissions": [str(uuid.uuid4())],
    }

    action = {
        "service_id": str(sample_service.id),
        "action_type": ADMIN_INVITE_USER,
        "action_data": action_data,
        "created_by": str(sample_user.id),
    }

    admin_request.post("admin_action.create_admin_action", action, _expected_status=201)

    actions = AdminAction.query.all()
    assert len(actions) == 1
    assert actions[0].service_id == sample_service.id
    assert actions[0].action_type == ADMIN_INVITE_USER
    assert actions[0].action_data == action_data
    assert actions[0].created_by_id == sample_user.id
    assert actions[0].created_at is not None
    assert actions[0].status == ADMIN_STATUS_PENDING
    assert actions[0].reviewed_by is None
    assert actions[0].reviewed_at is None


def test_get_all_pending_admin_actions(admin_request, sample_service, sample_user):
    create_admin_action(
        sample_service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "pending@test.com"}, "pending"
    )
    create_admin_action(
        sample_service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "approved@test.com"}, "approved"
    )
    create_admin_action(
        sample_service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "rejected@test.com"}, "rejected"
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
    assert pending[0]["service_id"] == str(sample_service.id)
    assert pending[0]["action_type"] == "invite_user"
    assert pending[0]["action_data"] == {"email_address": "pending@test.com"}
    assert pending[0]["created_by"] == str(sample_user.id)
    assert pending[0]["created_at"] is not None
    assert pending[0]["reviewed_by"] is None
    assert pending[0]["reviewed_at"] is None

    services = response["services"]
    assert len(services) == 1
    assert services[str(sample_service.id)]["id"] == str(sample_service.id)
    assert services[str(sample_service.id)]["name"] == str(sample_service.name)
    assert services[str(sample_service.id)]["restricted"] == sample_service.restricted

    users = response["users"]
    assert len(users) == 1
    assert users[str(sample_user.id)]["id"] == str(sample_user.id)
    assert users[str(sample_user.id)]["name"] == str(sample_user.name)
    assert users[str(sample_user.id)]["email_address"] == str(sample_user.email_address)


def test_get_pending_admin_elevation_action(admin_request, sample_user):
    """
    The elevation admin action is a little unique in that it doesn't have a service_id or populated action_data.
    This caused some issues during development so there's an extra test to be safe.
    """
    create_admin_action(None, sample_user.id, ADMIN_ELEVATE_USER, {}, "pending")
    response = admin_request.get("admin_action.get_pending_admin_actions", _expected_status=200)

    pending = response["pending"]

    assert len(pending) == 1
    assert pending[0]["service_id"] is None
    assert pending[0]["action_type"] == "elevate_platform_admin"
    assert pending[0]["action_data"] == {}
    assert pending[0]["created_by"] == str(sample_user.id)
    assert pending[0]["created_at"] is not None
    assert pending[0]["reviewed_by"] is None
    assert pending[0]["reviewed_at"] is None

    services = response["services"]
    assert len(services) == 0

    users = response["users"]
    assert len(users) == 1
    assert users[str(sample_user.id)]["id"] == str(sample_user.id)
    assert users[str(sample_user.id)]["name"] == str(sample_user.name)
    assert users[str(sample_user.id)]["email_address"] == str(sample_user.email_address)


def test_get_admin_action_by_id(admin_request, sample_service, sample_user):
    action = create_admin_action(
        sample_service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "pending@test.com"}, "pending"
    )

    response = admin_request.get("admin_action.get_admin_action_by_id", action_id=str(action.id))

    assert response["id"] == str(action.id)
    assert response["created_at"] is not None
    assert response["created_by"] == str(sample_user.id)
    assert response["action_type"] == ADMIN_INVITE_USER
    assert "email_address" in response["action_data"]
    assert response["status"] == ADMIN_STATUS_PENDING


@pytest.mark.parametrize("status, expected_response_code", (("pending", 200), ("approved", 400), ("rejected", 400)))
def test_only_pending_can_be_reviewed(status, expected_response_code, sample_service, admin_request, sample_user):
    action = create_admin_action(
        sample_service.id, sample_user.id, ADMIN_INVITE_USER, {"email_address": "test@test.com"}, status
    )

    review = {"status": "approved", "reviewed_by": str(sample_user.id)}

    admin_request.post(
        "admin_action.review_admin_action", review, action_id=str(action.id), _expected_status=expected_response_code
    )


@pytest.mark.parametrize(
    "existing_action_objs, proposed_action_obj, expect_conflict",
    [
        # User invites
        (
            [],
            {
                "action_type": "invite_user",
                "action_data": {
                    "email_address": "test@test.com",
                    "permissions": ["create_broadcasts"],
                    "login_authentication": "email_auth",
                    "folder_permissions": [str(uuid.uuid4())],
                },
            },
            False,
        ),
        (
            [
                [
                    {
                        "action_type": "invite_user",
                        "action_data": {
                            "email_address": "test@test.com",
                            "permissions": ["create_broadcasts"],
                            "login_authentication": "email_auth",
                            "folder_permissions": [str(uuid.uuid4())],
                        },
                    }
                ],
                {
                    "action_type": "invite_user",
                    "action_data": {
                        "email_address": "test@test.com",
                        "permissions": ["approve_broadcasts"],
                        "login_authentication": "email_auth",
                        "folder_permissions": [str(uuid.uuid4())],
                    },
                },
                True,
            ]
        ),
        (
            [
                [
                    {
                        "action_type": "invite_user",
                        "action_data": {
                            "email_address": "test@test.com",
                            "permissions": ["create_broadcasts"],
                            "login_authentication": "email_auth",
                            "folder_permissions": [str(uuid.uuid4())],
                        },
                    }
                ],
                {
                    "action_type": "invite_user",
                    "action_data": {
                        "email_address": "test2@test.com",
                        "permissions": ["approve_broadcasts"],
                        "login_authentication": "email_auth",
                        "folder_permissions": [str(uuid.uuid4())],
                    },
                },
                False,  # Different email
            ]
        ),
        # Edit permissions
        (
            [],
            {
                "action_type": "edit_permissions",
                "action_data": {
                    "user_id": "WILL_BE_REPLACED",
                    "existing_permissions": ["create_broadcasts"],
                    "permissions": ["create_broadcasts", "approve_broadcasts"],
                    "folder_permissions": [str(uuid.uuid4())],
                },
            },
            False,
        ),
        (
            [
                {
                    "action_type": "edit_permissions",
                    "action_data": {
                        "user_id": "WILL_BE_REPLACED",
                        "existing_permissions": ["create_broadcasts"],
                        "permissions": ["create_broadcasts", "approve_broadcasts"],
                        "folder_permissions": [str(uuid.uuid4())],
                    },
                }
            ],
            {
                "action_type": "edit_permissions",
                "action_data": {
                    "user_id": "WILL_BE_REPLACED",
                    "existing_permissions": ["create_broadcasts"],
                    "permissions": ["create_broadcasts", "approve_broadcasts", "manage_templates"],
                    "folder_permissions": [str(uuid.uuid4())],
                },
            },
            True,
        ),
        # API keys
        (
            [],
            {
                "action_type": "create_api_key",
                "action_data": {
                    "key_type": "normal",
                    "key_name": "New Key",
                },
            },
            False,
        ),
        (
            [
                {
                    "action_type": "create_api_key",
                    "action_data": {
                        "key_type": "normal",
                        "key_name": "New Key",
                    },
                }
            ],
            {
                "action_type": "create_api_key",
                "action_data": {
                    "key_type": "team",
                    "key_name": "New Key",
                },
            },
            True,
        ),
        # Admin elevation
        (
            [{"action_type": "elevate_platform_admin", "action_data": {}}],
            {"action_type": "elevate_platform_admin", "action_data": {}},
            # created_by is set in the test and remains static, so expect a conflict
            True,
        ),
    ],
)
def test_similar_admin_actions_are_rejected(
    existing_action_objs, proposed_action_obj, expect_conflict, admin_request, sample_user, sample_service
):
    """
    The Admin UI is expected to check for this scenario first and invalidate existing ones.
    This is just an enforcement of that.
    """

    # We need to inject IDs into the objects so that the DB foreign constraints can be satisfied.
    proposed_action_obj["created_by"] = str(sample_user.id)
    proposed_action_obj["service_id"] = str(sample_service.id)
    if proposed_action_obj["action_type"] == "edit_permissions":
        proposed_action_obj["action_data"]["user_id"] = str(sample_user.id)

    # Create an existing action (if present)
    for action in existing_action_objs:
        action_data = action.get("action_data")
        if action["action_type"] == "edit_permissions":
            action_data["user_id"] = str(sample_user.id)
        create_admin_action(sample_service.id, sample_user.id, action["action_type"], action_data, "pending")

    admin_request.post(
        "admin_action.create_admin_action", proposed_action_obj, _expected_status=409 if expect_conflict else 201
    )

    actions = AdminAction.query.all()
    if expect_conflict:
        assert len(actions) == len(existing_action_objs)
    else:
        assert len(actions) == len(existing_action_objs) + 1
