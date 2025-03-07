from emergency_alerts_utils.admin_action import (
    ADMIN_ACTION_LIST,
    ADMIN_CREATE_API_KEY,
    ADMIN_EDIT_PERMISSIONS,
    ADMIN_ELEVATE_USER,
    ADMIN_INVITE_USER,
    ADMIN_STATUS_LIST,
)
from emergency_alerts_utils.api_key import KEY_TYPES

from app.models import PERMISSION_LIST, USER_AUTH_TYPES
from app.schema_validation.definitions import uuid

create_admin_action_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create admin_action",
    "type": "object",
    "title": "Create admin_action",
    "properties": {
        "service_id": uuid,
        "created_by": uuid,
        "action_type": {"type": "string", "enum": ADMIN_ACTION_LIST},
        "action_data": {"type": "object"},
    },
    "required": ["created_by", "action_type", "action_data"],
    # Use the action_type to narrow down what is allowed in action_data and whether service_id is needed:
    "oneOf": [
        {
            "properties": {
                "action_type": {"const": ADMIN_INVITE_USER},
                "action_data": {
                    "type": "object",
                    "properties": {
                        "email_address": {"type": "string"},
                        "permissions": {"type": "array", "items": {"type": "string", "enum": PERMISSION_LIST}},
                        "login_authentication": {"type": "string", "enum": USER_AUTH_TYPES},
                        "folder_permissions": {"type": "array", "items": uuid},
                    },
                    "required": ["email_address", "permissions", "login_authentication", "folder_permissions"],
                },
            },
            "required": ["service_id"],
        },
        {
            "properties": {
                "action_type": {"const": ADMIN_EDIT_PERMISSIONS},
                "action_data": {
                    "type": "object",
                    "properties": {
                        "user_id": uuid,
                        "existing_permissions": {"type": "array", "items": {"type": "string", "enum": PERMISSION_LIST}},
                        "permissions": {"type": "array", "items": {"type": "string", "enum": PERMISSION_LIST}},
                        "folder_permissions": {"type": "array", "items": uuid},
                    },
                    "required": ["user_id", "permissions", "existing_permissions", "folder_permissions"],
                },
            },
            "required": ["service_id"],
        },
        {
            "properties": {
                "action_type": {"const": ADMIN_CREATE_API_KEY},
                "action_data": {
                    "type": "object",
                    "properties": {"key_type": {"type": "string", "enum": KEY_TYPES}, "key_name": {"type": "string"}},
                    "required": ["key_type", "key_name"],
                },
            },
            "required": ["service_id"],
        },
        {
            "properties": {
                "action_type": {"const": ADMIN_ELEVATE_USER}
                # No data - the created_by is the one requesting elevation for themselves
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
