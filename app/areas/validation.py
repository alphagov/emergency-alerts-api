def bulk_input_error_messages_by_geography_type(type_route):
    """
    Stored error messages for bulk area input by type_route.
    """
    if type_route == "flood_warning_areas":
        return {
            "missing_data": "Enter at least 1 Flood Warning TA code",
            "exceeds_limit": "Maximum of 25 TA codes in an emergency alert",
            "invalid": "Flood Warning TA code not found",
        }
    elif type_route == "local_authorities":
        return {
            "missing_data": "Enter at least 1 local authority",
            "duplicates": "All local authorities must be unique",
            "invalid": "Local authority not found",
            "exceeds_limit": "Maximum of 25 local authorities allowed as a list in one emergency alert",
        }
    else:
        return {
            "missing_data": "Enter at least 1 area",
            "duplicates": "Area names must be unique",
            "invalid": "Area not found",
            "exceeds_limit": "You can add no more than 25 areas",
        }


def validate_bulk_area_input(area_names, type_name):
    """
    Returns error message, or None, depending on whether list of area names provided is valid or not.
    """
    error_messages = bulk_input_error_messages_by_geography_type(type_name)

    # If no area_names posted
    if not area_names:
        return error_messages["missing_data"]

    # If duplicate area names posted, return the first duplicate value
    seen_area_names = set()
    duplicate_area_name = None

    for area_name in area_names:
        if area_name in seen_area_names:
            duplicate_area_name = area_name
            break
        seen_area_names.add(area_name)

    if duplicate_area_name is not None:
        if type_name == "flood_warning_areas":
            return f"Flood Warning TA code '{duplicate_area_name}' appears in the list more than once"
        elif type_name == "local_authorities":
            return f"Local authority '{duplicate_area_name}' currently appears in the list more than once"

        return error_messages["duplicates"]

    # We can't add more than 25 areas at a time for bulk input
    if len(area_names) > 25:
        return error_messages["exceeds_limit"]

    return None
