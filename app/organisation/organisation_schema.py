from app.models import INVITED_USER_STATUS_TYPES, ORGANISATION_TYPES
from app.schema_validation.definitions import uuid

post_create_organisation_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST organisation schema",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "active": {"type": ["boolean", "null"]},
        "crown": {"type": "boolean"},
        "organisation_type": {"enum": ORGANISATION_TYPES},
    },
    "required": ["name", "crown", "organisation_type"],
}

post_update_organisation_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST organisation schema",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "active": {"type": ["boolean", "null"]},
        "crown": {"type": ["boolean", "null"]},
        "organisation_type": {"enum": ORGANISATION_TYPES},
    },
    "required": [],
}

post_link_service_to_organisation_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST link service to organisation schema",
    "type": "object",
    "properties": {"service_id": uuid},
    "required": ["service_id"],
}


post_create_invited_org_user_status_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create organisation invite schema",
    "type": "object",
    "properties": {
        "email_address": {"type": "string", "format": "email_address"},
        "invited_by": uuid,
        "invite_link_host": {"type": "string"},
    },
    "required": ["email_address", "invited_by"],
}


post_update_invited_org_user_status_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update organisation invite schema",
    "type": "object",
    "properties": {"status": {"enum": INVITED_USER_STATUS_TYPES}},
    "required": ["status"],
}


# post_update_org_email_branding_pool_schema = {
#     "$schema": "http://json-schema.org/draft-07/schema#",
#     "description": "POST update organisation email branding pool schema",
#     "type": "object",
#     "properties": {"branding_ids": {"type": "array", "items": uuid}},
#     "required": ["branding_ids"],
# }


# post_update_org_letter_branding_pool_schema = {
#     "$schema": "http://json-schema.org/draft-07/schema#",
#     "description": "POST update organisation letter branding pool schema",
#     "type": "object",
#     "properties": {"branding_ids": {"type": "array", "items": uuid}},
#     "required": ["branding_ids"],
# }
