from app.models import TEMPLATE_TYPES
from app.schema_validation.definitions import uuid

post_create_template_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new template",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template",
    "properties": {
        "name": {"type": "string"},
        "template_type": {"enum": TEMPLATE_TYPES},
        "service": uuid,
        "content": {"type": "string"},
        "created_by": uuid,
        "parent_folder_id": uuid,
    },
    "required": ["name", "template_type", "content", "service", "created_by"],
}

post_update_template_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update existing template",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template/<uuid:template_id>",
    "properties": {
        "id": uuid,
        "name": {"type": "string"},
        "template_type": {"enum": TEMPLATE_TYPES},
        "service": uuid,
        "content": {"type": "string"},
        "created_by": uuid,
        "archived": {"type": "boolean"},
        "current_user": uuid,
    },
}
