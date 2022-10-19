from app.models import BRANDING_TYPES

post_create_email_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "text": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]},
        "brand_type": {"enum": BRANDING_TYPES},
        "created_by": {"type": ["string"], "required": False},
    },
    "required": ["name"],
}

post_update_email_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]},
        "brand_type": {"enum": BRANDING_TYPES},
        "updated_by": {"type": ["string"], "required": False},
    },
    "required": [],
}
