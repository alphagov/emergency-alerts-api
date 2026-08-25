import shapely
from emergency_alerts_utils.polygons import Polygons
from flask import Blueprint, jsonify, request
from geoalchemy2.shape import to_shape

from app.areas.utils import (
    add_custom_area_to_existing_areas,
    area_response_json,
    build_circle_area,
    build_remaining_area_wkt,
    bulk_input_error_messages_by_geography_type,
    create_alert_area_dict,
    ensure_valid_wkt,
    generate_centroid_for_coordinate_area,
    generate_coordinate_area_name,
    get_existing_area_data,
    parse_coordinate_id,
    parse_postcode_id,
    validate_bulk_area_input,
)
from app.dao.areas_dao import (
    dao_check_coordinates_valid,
    dao_combine_geometries,
    dao_create_area,
    dao_create_circle_area,
    dao_get_area_by_id,
    dao_get_area_centroid,
    dao_get_areas_by_ids,
    dao_get_areas_by_names,
    dao_get_areas_for_geography_type,
    dao_get_child_areas_for_parent_geography_id,
    dao_get_grandparent_areas,
    dao_get_latest_area_by_geographic_id,
    dao_get_latest_geography_types_with_count_and_examples,
)
from app.dao.broadcast_message_dao import (
    dao_get_broadcast_message_by_id_and_service_id,
)
from app.dao.broadcast_message_history_dao import (
    dao_create_broadcast_message_version,
)
from app.dao.dao_utils import dao_save_object
from app.dao.templates_dao import (
    dao_get_template_by_id_and_service_id,
    dao_update_template,
)
from app.schemas import template_schema

areas_blueprint = Blueprint(
    "areas",
    __name__,
    url_prefix="/areas",
)


@areas_blueprint.route("/<area_id>", methods=["GET"])
def get_area(area_id):
    """
    Retrieves area from area ID.
    """
    result = dao_get_area_by_id(area_id)
    if result is None:
        return jsonify({"message": "No area with this ID"}), 400
    data = area_response_json(result)

    return jsonify({"data": data})


@areas_blueprint.route("/geographic_id/<geographic_id>", methods=["GET"])
def get_area_by_geographic_id_endpoint(geographic_id):
    """
    Returns the latest area for a certain geographic ID.
    """
    result = dao_get_latest_area_by_geographic_id(geographic_id)
    if result is None:
        return jsonify({"message": "No area retrieved for this geographic ID."}), 400

    data = area_response_json(result)

    return jsonify({"data": data})


@areas_blueprint.route("/get-areas", methods=["POST"])
def get_areas():
    data = request.get_json() or {}
    area_ids = data.get("area_ids") or []
    area_names = data.get("area_names") or []

    # Areas from alerts, created prior to this change, will have area IDs that we don't store
    legacy_prefixes = (
        "ctry19-",
        "Flood_Warning_Target_Areas-",
        "wd25-",
        "test-",
        "lad25-",
        "ctyua25-",
    )

    id_to_name = dict(zip(area_ids, area_names))

    predefined_area_ids = []
    circle_ids = []  # Postcode and Coordinate areas that we generate ourselves, from IDs
    legacy_ids = []  # IDs starting with legacy_prefixes

    for area_id in area_ids:
        if area_id.startswith("postcodes"):
            circle_ids.append((area_id, "postcodes"))
        elif area_id.startswith("coordinates"):
            circle_ids.append((area_id, "coordinates"))
        elif area_id.startswith(legacy_prefixes):
            legacy_ids.append(area_id)
        else:
            # If not circle (postcode or coordinate areas) or legacy, then
            # we assume it is an area we have predefined in geography_polygona
            predefined_area_ids.append(area_id)

    data = []

    if predefined_area_ids:
        predefined_results = dao_get_areas_by_ids(predefined_area_ids)
        data.extend(area_response_json(row) for row in predefined_results)

    for legacy_id in legacy_ids:
        # Removes legacy prefix and uses the remainder (geographic ID) to source area
        _, geographic_id = legacy_id.split("-", 1)
        row = dao_get_latest_area_by_geographic_id(geographic_id)
        if row is None:
            return jsonify({"message": "No area could be found for this geographic ID"}), 400
        data.append(area_response_json(row))

    # Generate postcode and coordinate areas to be stored
    for area_id, geography_type in circle_ids:
        data.append(build_circle_area(area_id, geography_type, id_to_name))

    return jsonify({"data": data})


@areas_blueprint.route("/<area_id>/is-grandparent", methods=["GET"])
def is_grandparent(area_id):
    """Returns bool for whether or not an area is a grandparent area, i.e.
    is a parent of an area that is also a parent"""
    grandparent_areas = [str(i[0]) for i in dao_get_grandparent_areas()]
    return jsonify({"data": area_id in grandparent_areas})


@areas_blueprint.route("/geography-types", methods=["GET"])
def get_geography_types_and_examples():
    """Returns a list of geography types/libraries (dicts), for rendering in Admin application"""
    results = dao_get_latest_geography_types_with_count_and_examples()
    data = []

    for row in results:
        # For each geography type (library)
        area_names = list(row.areas or [])  # Geography type's areas
        count = int(row.area_count or 0)  # Count of areas for geography type

        # Generates examples string to be displayed on Admin
        # applications 'libraries' page
        if count <= 4:
            examples = ", ".join(area_names)
        else:
            shown = area_names[:3]
            remaining = count - 3
            examples = f"{', '.join(shown)} and {remaining} more..."

        data.append(
            {
                "id": row.id,
                "name": row.geography_type_name,
                "name_singular": row.name_singular,
                "route": row.route,
                "examples": examples,
            }
        )

    return jsonify({"data": data})


@areas_blueprint.route("/geography-types/<type_name>/areas", methods=["GET"])
def get_areas_for_type(type_name):
    """Returns list of areas for a geography type/library"""
    results = dao_get_areas_for_geography_type(type_name)
    areas = [
        {"id": row.id, "geographic_id": row.geographic_id, "name": row.name, "parent": row.parent_geography_id}
        for row in results
    ]
    return jsonify({"data": areas})


@areas_blueprint.route("/<parent_geography_id>/sub-areas", methods=["GET"])
def get_child_areas_for_parent(parent_geography_id):
    """Returns list of areas with specified parent_geography_id"""
    results = dao_get_child_areas_for_parent_geography_id(parent_geography_id)
    areas = [
        {"id": row.id, "geographic_id": row.geographic_id, "name": row.name, "is_parent": row.parent_geography_id}
        for row in results
    ]

    return jsonify({"data": areas})


@areas_blueprint.route("/postcodes/get-centroid", methods=["POST"])
def get_postcode_centroid():
    """
    Returns the centroid WKT for the specific postcode.
    """
    data = request.get_json() or {}
    postcode = data.get("postcode")

    postcode_area = dao_get_latest_area_by_geographic_id(postcode, "postcodes")
    if not postcode_area:
        return jsonify({"message": "Enter a postcode within the UK"}), 400

    centroid = dao_get_area_centroid(postcode_area.id)
    if centroid is None:
        return jsonify({"message": "Area has no geometry"}), 400

    return jsonify({"data": centroid})


@areas_blueprint.route("/coordinates/get-centroid", methods=["POST"])
def get_coordinates_centroid():
    """
    Returns a centroid WKT for the provided coordinates.
    """
    data = request.get_json() or {}
    first_coordinate = data.get("first_coordinate")
    second_coordinate = data.get("second_coordinate")
    coordinate_type = data.get("coordinate_type")

    if not dao_check_coordinates_valid(first_coordinate, second_coordinate, coordinate_type):
        return jsonify({"message": "Enter coordinates within the UK"}), 400

    centroid = generate_centroid_for_coordinate_area(first_coordinate, second_coordinate, coordinate_type)

    return jsonify({"data": centroid})


@areas_blueprint.route("/get-<type_name>-by-names", methods=["POST"])
def get_local_authorities_areas_by_names(type_name):
    """Returns a list of areas that have the names provided for the provided type,
    or error response with custom error messages set for local_authorities areas."""
    data = request.get_json() or {}
    area_names = data.get("area_names") or []

    # Filters possible error messages by geography type
    error_messages = bulk_input_error_messages_by_geography_type(type_name)

    if error_response := validate_bulk_area_input(area_names, type_name):
        return jsonify({"message": error_response}), 400

    areas = dao_get_areas_by_names(area_names, type_name)
    found_by_name = {area.name: area.id for area in areas}

    # Returns 400 error for a missing name - error to then be
    # rendered as is in Admin application
    for name in area_names:
        if name not in found_by_name:
            return (
                jsonify(
                    {
                        "message": error_messages["invalid"],
                        "missing_area_name": name,
                        "geography_type": type_name,
                    }
                ),
                400,
            )

    ids = [found_by_name[name] for name in area_names]
    return jsonify({"data": ids})


@areas_blueprint.route("/postcode-area", methods=["POST"])
def create_postcode_area():
    """Returns WKT string of created postcode area, created using radius and
    centroid of the latest polygon for the specified postcode boundary"""
    data = request.get_json()
    radius = data.get("radius")
    postcode = data.get("postcode")
    postcode_area_id = dao_get_latest_area_by_geographic_id(postcode, "postcodes").id
    centroid = dao_get_area_centroid(postcode_area_id)
    circle = dao_create_circle_area(centroid, radius)
    centroid_wkt = shapely.wkt.loads(centroid)
    id = f"postcodes_{centroid_wkt.x}_{centroid_wkt.y}_{radius}_{postcode}"
    return jsonify({"circle": circle, "id": id})


@areas_blueprint.route("/coordinate-area", methods=["POST"])
def create_coordinate_area():
    """Returns WKT string of created coordinate area, created using radius and
    centroid, formed from specified coordinates"""
    data = request.get_json()
    first_coordinate = data.get("first_coordinate")
    second_coordinate = data.get("second_coordinate")
    coordinate_type = data.get("coordinate_type")
    radius = float(data.get("radius"))

    if not dao_check_coordinates_valid(first_coordinate, second_coordinate, coordinate_type):
        return jsonify({"message": "Enter coordinates within the UK"}), 400

    centroid = generate_centroid_for_coordinate_area(first_coordinate, second_coordinate, coordinate_type)
    circle = dao_create_circle_area(centroid, radius)
    return jsonify(
        {
            "data": circle,
        }
    )


@areas_blueprint.route("/check-coordinates-valid", methods=["POST"])
def check_coordinates_valid():
    """Returns boolean result of whether or not the specified
    coordinates lie within UK polygon area"""
    data = request.get_json()
    first = data.get("first_coordinate")
    second = data.get("second_coordinate")
    coordinate_type = data.get("coordinate_type")
    valid = dao_check_coordinates_valid(first, second, coordinate_type)
    return jsonify(
        {
            "data": valid,
        }
    )


@areas_blueprint.route("/get-area-dict", methods=["POST"])
def build_alert_area_for_ids():
    """
    Returns area dictionary for an alert, based on specified area IDs.
    Names are sourced from the database for predefined areas and
    generated for postcode/coordinate areas.
    """
    data = request.get_json() or {}
    area_ids = data.get("area_ids") or []

    if not area_ids:
        # If no area IDs, return empty area dictionary
        return (
            jsonify(create_alert_area_dict()),
            200,
        )

    predefined_area_ids = []
    postcode_ids = []
    coordinate_ids = []

    # Splits specified area IDs into appropriate lists, to be processed accordingly
    for area_id in area_ids:
        if area_id.startswith("postcodes"):
            postcode_ids.append(area_id)
        elif area_id.startswith("coordinates"):
            coordinate_ids.append(area_id)
        else:
            predefined_area_ids.append(area_id)

    geometries_wkt = []
    names = []

    # For predefined areas, source area polygons and append to list of geometries
    if predefined_area_ids:
        predefined_areas = dao_get_areas_by_ids(set(predefined_area_ids))
        geometries_wkt.extend([to_shape(a.geometry).wkt for a in predefined_areas])
        names.extend([a.name for a in predefined_areas])

    for postcode_id in postcode_ids:
        # Split the postcode ID into centroid coordinates and radius of area
        x, y, radius, postcode = parse_postcode_id(postcode_id)
        centroid = shapely.Point(x, y).wkt
        circle_wkt = dao_create_circle_area(centroid, radius)
        geometries_wkt.append(circle_wkt)
        names.append(f"{radius}km around the postcode {postcode}")

    for coordinate_id in coordinate_ids:
        # Split the coordinate ID into centroid coordinates and radius of area
        x, y, radius, coordinate_type = parse_coordinate_id(coordinate_id)
        centroid = generate_centroid_for_coordinate_area(x, y, coordinate_type)
        name = generate_coordinate_area_name(x, y, radius, coordinate_type)
        circle_wkt = dao_create_circle_area(centroid, radius)
        geometries_wkt.append(circle_wkt)
        names.append(name)

    # Combine all of the geometries then validate the combined WKT
    combined_wkt = dao_create_area(geometries_wkt)
    combined_wkt = ensure_valid_wkt(combined_wkt)

    # From WKT, Polygons object (from emergency-alerts-utils) returned
    polygons = Polygons.from_wkt(combined_wkt, utm_crs="EPSG:4326")
    alert_area = create_alert_area_dict(area_ids, names, polygons.polygons)
    return jsonify(alert_area), 200


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/add-areas", methods=["POST"])
def add_areas(service_id, message_id, message_type):
    data = request.get_json() or {}
    area_ids = data.get("area_ids") or []
    type_name = data.get("type_name")

    # The following are inner functions that have been extracted as they are called at
    # least once for both broadcast messages and templates
    def process_flood_warning_area_ids(raw_ids, existing_ids, error_messages):
        # Flood Warning Area ID input validation and if valid, they are appended to alert areas
        if error_response := validate_bulk_area_input(raw_ids, type_name):
            return None, jsonify({"message": error_response}), 400

        sourced_ids = []
        for original_id in raw_ids:
            area = dao_get_latest_area_by_geographic_id(original_id)
            if area is None:
                return None, jsonify({"message": error_messages["invalid"]}), 400

            area_id = str(area.id)
            if area_id in existing_ids:
                return None, jsonify({"message": error_messages["already_selected"]}), 400

            sourced_ids.append(area_id)

        return sourced_ids, None, None

    def build_combined_alert_area(existing_ids, existing_names, existing_polygons, new_area_ids):
        # Combines the existing areas and the new areas, by sourcing the WKT for
        # each new area and combining with existing alert area WKT
        areas = dao_get_areas_by_ids(set(new_area_ids))
        names = [area.name for area in areas]
        new_area_wkts = [to_shape(area.geometry).wkt for area in areas]
        new_areas_combined_wkt = dao_create_area(new_area_wkts)

        # Reversed as utils requires the area polygons to be long, lat NOT lat, long
        reversed_polygons = [[[coord[1], coord[0]] for coord in polygon] for polygon in existing_polygons]
        existing_wkt = Polygons(polygons=reversed_polygons).as_wkt

        combined_wkt = dao_combine_geometries(existing_wkt, new_areas_combined_wkt)
        combined_wkt = ensure_valid_wkt(combined_wkt)

        polygons = Polygons.from_wkt(combined_wkt, utm_crs="EPSG:4326")

        combined_ids = existing_ids + new_area_ids
        combined_names = existing_names + names
        return create_alert_area_dict(combined_ids, combined_names, polygons.polygons)

    def add_areas_to_broadcast_message():
        broadcast_message = dao_get_broadcast_message_by_id_and_service_id(message_id, service_id)
        existing_ids, existing_names, existing_polygons = get_existing_area_data(broadcast_message)

        # Sources the error messages for rendering if bulk area input invalid
        error_messages = bulk_input_error_messages_by_geography_type(type_name)

        flood_warning_area_ids = area_ids
        if type_name == "flood_warning_areas":
            flood_warning_area_ids, error_response, status = process_flood_warning_area_ids(
                area_ids, existing_ids, error_messages
            )
            if error_response:
                return error_response, status

        # Areas to be added are only those predefined that are not already added to alert
        areas_to_be_added = [area for area in (flood_warning_area_ids or area_ids) if area not in existing_ids]
        if not areas_to_be_added:
            return jsonify(broadcast_message.serialize()), 200

        alert_area = build_combined_alert_area(existing_ids, existing_names, existing_polygons, areas_to_be_added)
        broadcast_message.areas = alert_area

        dao_save_object(broadcast_message)
        dao_create_broadcast_message_version(
            broadcast_message,
            service_id,
            broadcast_message.updated_by_id,
        )
        return jsonify(broadcast_message.serialize()), 200

    def add_areas_to_template():
        template = dao_get_template_by_id_and_service_id(message_id, service_id)
        existing_ids, existing_names, existing_polygons = get_existing_area_data(template)

        # Sources the error messages for rendering if bulk area input invalid
        error_messages = bulk_input_error_messages_by_geography_type(type_name)

        flood_ids = area_ids
        if type_name == "flood_warning_areas":
            flood_ids, error_response, status = process_flood_warning_area_ids(area_ids, existing_ids, error_messages)
            if error_response:
                return error_response, status

        # Areas to be added are only those predefined that are not already added to alert
        areas_to_be_added = [area for area in (flood_ids or area_ids) if area not in existing_ids]
        if not areas_to_be_added:
            return jsonify(template_schema.dump(template)), 200

        alert_area = build_combined_alert_area(existing_ids, existing_names, existing_polygons, areas_to_be_added)

        current_data = dict(template_schema.dump(template).items())
        updated_template_data = dict(current_data)
        updated_template_data["areas"] = alert_area

        update_dict = template_schema.load(updated_template_data)
        if update_dict.archived:
            update_dict.folder = None

        dao_update_template(update_dict)
        return jsonify(data=template_schema.dump(update_dict)), 200

    if message_type == "broadcast":
        return add_areas_to_broadcast_message()
    elif message_type == "templates":
        return add_areas_to_template()


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/add-<type_name>-area", methods=["POST"])
def add_custom_areas(service_id, message_id, message_type, type_name):
    """Uses specified custom area IDS, parses based on `type_name`,
    creates the custom area and adds to the broadcast_message or template"""
    data = request.get_json() or {}

    def add_custom_areas_to_broadcast_message(service_id, message_id, type_name, data):
        broadcast_message = dao_get_broadcast_message_by_id_and_service_id(message_id, service_id)
        updated_message, error_response, status = add_custom_area_to_existing_areas(broadcast_message, type_name, data)
        if error_response:
            return error_response, status

        dao_save_object(updated_message)
        dao_create_broadcast_message_version(
            updated_message,
            service_id,
            updated_message.updated_by_id,
        )
        return jsonify(updated_message.serialize()), 200

    def add_custom_areas_to_template(service_id, template_id, type_name, data):
        template = dao_get_template_by_id_and_service_id(template_id, service_id)

        updated_template, error_response, status = add_custom_area_to_existing_areas(template, type_name, data)
        if error_response:
            return error_response, status

        # Save updated template
        dao_save_object(updated_template)

        # Build an updated_template dict like update_template does,
        # using the updated template and its new areas data
        current_data = dict(template_schema.dump(updated_template).items())
        alert_area = updated_template.areas or {}
        current_data["areas"] = alert_area

        update_dict = template_schema.load(current_data)
        if update_dict.archived:
            update_dict.folder = None
        dao_update_template(update_dict)
        return jsonify(template_schema.dump(update_dict)), 200

    if message_type == "broadcast":
        return add_custom_areas_to_broadcast_message(service_id, message_id, type_name, data)
    elif message_type == "templates":
        return add_custom_areas_to_template(service_id, message_id, type_name, data)

    return jsonify({"message": "Unsupported message_type"}), 400


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/remove-area", methods=["POST"])
def remove_area(service_id, message_id, message_type):
    """Identifies the area IDs remaining once specified area IDs are removed,
    then with these calculates the remaining area for the alert"""
    data = request.get_json() or {}
    area_id_to_remove = data.get("area_id") or []

    def build_remaining_alert_areas(area_id_to_remove, existing_ids, existing_names):
        new_ids, new_polygons, any_remaining = build_remaining_area_wkt(existing_ids, area_id_to_remove)
        if not any_remaining:
            return create_alert_area_dict()

        new_names = [name for id, name in zip(existing_ids, existing_names) if id != area_id_to_remove]
        return create_alert_area_dict(new_ids, new_names, new_polygons)

    if message_type == "broadcast":
        broadcast_message = dao_get_broadcast_message_by_id_and_service_id(message_id, service_id)
        existing_ids, existing_names, existing_polygons = get_existing_area_data(broadcast_message)

        broadcast_message.areas = build_remaining_alert_areas(area_id_to_remove, existing_ids, existing_names)

        dao_save_object(broadcast_message)
        dao_create_broadcast_message_version(
            broadcast_message,
            service_id,
            broadcast_message.updated_by_id,
        )
        return jsonify(broadcast_message.serialize()), 200

    elif message_type == "templates":
        template = dao_get_template_by_id_and_service_id(message_id, service_id)
        existing_ids, existing_names, existing_polygons = get_existing_area_data(template)

        alert_area = build_remaining_alert_areas(area_id_to_remove, existing_ids, existing_names)

        current_data = dict(template_schema.dump(template).items())
        updated_template_data = dict(current_data)
        updated_template_data["areas"] = alert_area

        update_dict = template_schema.load(updated_template_data)
        if update_dict.archived:
            update_dict.folder = None

        dao_update_template(update_dict)
        return jsonify(data=template_schema.dump(update_dict)), 200
