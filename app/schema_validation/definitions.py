"""
Definitions are intended for schema definitions that are not likely to change from version to version.
If the definition is specific to a version put it in a definition file in the version package
"""

uuid = {
    "type": "string",
    "format": "validate_uuid",
    "validationMessage": "is not a valid UUID",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented",
}

nullable_uuid = {
    "type": ["string", "null"],
    "format": "validate_uuid",
    "validationMessage": "is not a valid UUID",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented",
}


personalisation = {
    "type": "object",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented",
}


https_url = {
    "type": "string",
    "format": "uri",
    "pattern": "^https.*",
    "validationMessage": "is not a valid https url",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented",
}


coordinate_pair = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 2,
    "maxItems": 2,
}

# A closed ring: the first and last coordinate pairs are the same, so a triangle has 4 points
polygon = {
    "type": "array",
    "minItems": 4,
    "items": coordinate_pair,
}

# The stored shape of BroadcastMessage.areas. The admin app sends all four properties; alerts
# created through the v2 API only have names and simple_polygons. The arrays can be empty while
# an alert is still a draft.
broadcast_areas = {
    "type": "object",
    "required": ["names", "simple_polygons"],
    "properties": {
        "ids": {"type": "array", "items": {"type": "string"}},
        "names": {"type": "array", "items": {"type": "string"}},
        "aggregate_names": {"type": "array", "items": {"type": "string"}},
        "simple_polygons": {"type": "array", "items": polygon},
    },
}

# The shape an alert's areas must have once it has been broadcast, and is published to gov.uk/alerts
live_broadcast_areas = {
    **broadcast_areas,
    "properties": {
        **broadcast_areas["properties"],
        "names": {**broadcast_areas["properties"]["names"], "minItems": 1},
        "simple_polygons": {**broadcast_areas["properties"]["simple_polygons"], "minItems": 1},
    },
}
