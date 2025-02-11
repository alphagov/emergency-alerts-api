from app.models import (
    ADMIN_ACTION_LIST,
    ADMIN_INVITE_USER,
    ADMIN_INVITE_USER_ORG,
    ADMIN_STATUS_LIST,
    PERMISSION_LIST,
)
from app.schema_validation.definitions import uuid

create_admin_action_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create admin_action",
    "type": "object",
    "title": "Create admin_action",
    "properties": {
        "organisation_id": uuid,
        "service_id": uuid,
        "created_by": uuid,
        "action_type": {"type": "string", "enum": ADMIN_ACTION_LIST},
        "action_data": {"type": "object"},
    },
    "required": ["organisation_id", "created_by", "action_type", "action_data"],
    # Use the action_type to narrow down what is allowed in action_data:
    "oneOf": [
        {
            "properties": {
                "action_type": {"const": ADMIN_INVITE_USER_ORG},
                "action_data": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                    },
                    "required": ["email"],
                },
            }
        },
        {
            "required": ["service_id"],  # A non-org invite must be against a service
            "properties": {
                "action_type": {"const": ADMIN_INVITE_USER},
                "action_data": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "permissions": {"type": "array", "items": {"type": "string", "enum": PERMISSION_LIST}},
                    },
                    "required": ["email", "permissions"],
                },
            },
        },
    ],
    "additionalProperties": False,
}

review_admin_action_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST review admin_action",
    "type": "object",
    "title": "Review admin_action",
    "properties": {"reviewed_by": uuid, "status": {"type": "string", "enum": ADMIN_STATUS_LIST}},
    "required": ["reviewed_by", "status"],
    "additionalProperties": False,
}
