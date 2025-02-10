import uuid

import pytest
from jsonschema import ValidationError

from app.admin_action.admin_action_schema import create_admin_action_schema
from app.schema_validation import validate


@pytest.mark.parametrize(
    "under_test",
    [
        {
            "organisation_id": str(uuid.uuid4()),
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {"email": "test@test.com", "permissions": ["create_broadcasts"]},
        },
        {
            "organisation_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user_org",
            "action_data": {"email": "test@test.com"},
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
            "organisation_id": str(uuid.uuid4()),
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invalid_action",
            "action_data": {},
        },
        {
            "organisation_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",  # Missing service_id
            "action_data": {"email": "test@test.com", "permissions": ["create_broadcasts"]},
        },
        {
            "organisation_id": str(uuid.uuid4()),
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {"email": "test@test.com", "permissions": ["invalid"]},
        },
        {
            "organisation_id": str(uuid.uuid4()),
            "service_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user",
            "action_data": {"not_an_email_field": "test@test.com", "permissions": ["create_broadcasts"]},
        },
        {
            "organisation_id": str(uuid.uuid4()),
            "created_by": str(uuid.uuid4()),
            "action_type": "invite_user_org",
            "action_data": {"not_an_email_field": "test@test.com"},
        },
    ],
)
def test_negative_schema_validation(under_test):
    with pytest.raises(ValidationError):
        validate(under_test, create_admin_action_schema)
