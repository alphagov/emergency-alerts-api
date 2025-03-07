import uuid

import pytest
from jsonschema import ValidationError

from app.admin_action.admin_action_schema import create_admin_action_schema
from app.schema_validation import validate


@pytest.mark.parametrize(
    "under_test",
    [
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {
                "email_address": "test@test.com",
                "permissions": ["create_broadcasts"],
                "login_authentication": "email_auth",
                "folder_permissions": [str(uuid.uuid4())],
            },
        },
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "edit_permissions",
            "action_data": {
                "user_id": str(uuid.uuid4()),
                "existing_permissions": ["create_broadcasts"],
                "permissions": ["create_broadcasts", "approve_broadcasts"],
                "folder_permissions": [str(uuid.uuid4())],
            },
        },
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "create_api_key",
            "action_data": {
                "key_type": "normal",
                "key_name": "New Key",
            },
        },
        {
            "created_by": str(uuid.uuid4()),
            "action_type": "elevate_platform_admin",
            "action_data": {},
        },
    ],
)
def test_positive_schema_validation(under_test):
    validated = validate(under_test, create_admin_action_schema)
    assert validated == under_test


@pytest.mark.parametrize(
    "under_test",
    [
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invalid_action",
            "action_data": {},
        },
        {
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",  # Missing service_id
            "action_data": {
                "email_address": "test@test.com",
                "permissions": ["create_broadcasts"],
                "folder_permissions": [str(uuid.uuid4())],
            },
        },
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {
                "email_address": "test@test.com",
                "permissions": ["invalid"],
                "folder_permissions": [str(uuid.uuid4())],
            },
        },
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {
                "not_an_email_field": "test@test.com",
                "permissions": ["create_broadcasts"],
                "folder_permissions": [str(uuid.uuid4())],
            },
        },
        {
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {
                "email_address": "test@test.com",
                "permissions": ["create_broadcasts"],
            },
        },
        {
            "created_by": str(uuid.uuid4()),
            "action_type": "elevate_platform_admin",
            # action_data is required but must be empty
        },
    ],
)
def test_negative_schema_validation(under_test):
    with pytest.raises(ValidationError):
        validate(under_test, create_admin_action_schema)
