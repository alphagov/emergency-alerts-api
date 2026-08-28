import shapely
from emergency_alerts_utils.polygons import Polygons
from flask import jsonify
from geoalchemy2.shape import to_shape
from pyproj import Transformer

from app.dao.areas_dao import (
    dao_combine_geometries,
    dao_create_area,
    dao_create_circle_area,
    dao_get_area_by_id,
    dao_get_area_centroid,
    dao_get_areas_by_ids,
    dao_get_dominant_parent_geography_id,
    dao_get_latest_area_by_geographic_id,
)


def area_response_json(area_object):
    return {
        "id": area_object.id,
        "name": area_object.name,
        "parent": area_object.parent_geography_id,
        "geographic_id": area_object.geographic_id,
        "geography_type": area_object.geography_type_name,
    }


def generate_coordinate_area_name(x, y, radius, coordinate_type):
    if coordinate_type == "latitude_longitude":
        name = f"{radius:g}km around {x} latitude, {y} longitude"
    elif coordinate_type == "easting_northing":
        name = f"{radius:g}km around {x} easting, {y} northing"
    return name


def parse_coordinate_id(area_id):
    """Coordinate area IDs are stored in the following format
    `coordinates_{x coordinate}_{y coordinate}_{radius}_{coordinate_type}`.
    Where the coordinate_type is either latitude_longitude or eastings_northing
    and is required to determine whether transformation is needed.
    this function splits the ID into the following values"""
    _, x_coordinate, y_coordinate, radius, coordinate_type = area_id.split("_", 4)
    return float(x_coordinate), float(y_coordinate), float(radius), coordinate_type


def parse_postcode_id(area_id):
    """Postcode area IDs are stored in the following format
    `postcodes_{x coordinate}_{y coordinate}_{radius}_{postcode ID}`,
    where postcode ID is the postcode as is e.g. AB10 1AL.
    This function splits the ID into the following values"""
    _, x_coordinate, y_coordinate, radius, postcode = area_id.split("_", 4)
    return float(x_coordinate), float(y_coordinate), float(radius), postcode


def build_circle_area(area_id, geography_type, id_to_name):
    return {
        "id": area_id,
        "name": id_to_name.get(area_id),
        "geographic_id": area_id,
        "geography_type": geography_type,
    }


def get_parent_geography_id(area_wkt, parent_type_name="local_authorities"):
    """Retrieves the parent geography ID either from DB, if exists, or by
    calculating the most intersecting area from areas with specified type"""
    return dao_get_dominant_parent_geography_id(area_wkt, parent_type_name)


def add_custom_area_to_existing_areas(message, type_name, data):
    radius = float(data.get("radius")) if data.get("radius") is not None else None
    area_id = None
    if radius is None:
        return None, jsonify({"message": "radius is required for circle areas"}), 400

    existing_ids, existing_names, existing_polygons = get_existing_area_data(message)

    # Build centroid, area_id and name based on type
    if type_name == "postcodes":
        postcode = data.get("postcode")
        postcode_area_id = dao_get_latest_area_by_geographic_id(postcode, "postcodes").id
        centroid = dao_get_area_centroid(postcode_area_id)
        centroid_wkt = shapely.wkt.loads(centroid)
        area_id = f"postcodes_{centroid_wkt.x}_{centroid_wkt.y}_{radius}_{postcode}"
        name = f"{radius:g}km around the postcode {postcode}"

    elif type_name == "coordinates":
        first_coordinate = data.get("first_coordinate")
        second_coordinate = data.get("second_coordinate")
        coordinate_type = data.get("coordinate_type")
        centroid = generate_centroid_for_coordinate_area(first_coordinate, second_coordinate, coordinate_type)
        name = generate_coordinate_area_name(first_coordinate, second_coordinate, radius, coordinate_type)
        if parent_area := get_parent_area_name(centroid):
            name = f"{name} in {parent_area}"
        centroid_wkt = shapely.wkt.loads(centroid)
        area_id = f"coordinates_{centroid_wkt.y}_{centroid_wkt.x}_{radius}_{coordinate_type}"

    # Prevent duplicate areas: if area_id already exists, return unchanged
    if area_id and area_id in existing_ids:
        return message, None, None

    circle_wkt = dao_create_circle_area(centroid, radius)

    reversed_polygons = [[[coord[1], coord[0]] for coord in polygon] for polygon in existing_polygons]
    existing_wkt = Polygons(polygons=reversed_polygons).as_wkt

    new_areas = dao_create_area([circle_wkt])
    combined_wkt = dao_combine_geometries(existing_wkt, new_areas)
    combined_wkt = ensure_valid_wkt(combined_wkt)

    polygons = Polygons.from_wkt(combined_wkt, utm_crs="EPSG:4326")

    combined_ids = existing_ids + [area_id]
    combined_names = existing_names + [name]
    alert_area = create_alert_area_dict(combined_ids, combined_names, polygons.polygons)

    message.areas = alert_area
    return message, None, None


def get_parent_area_name(centroid):
    """
    Gets `parent_geography_id`, retrieves the area with this ID
    and then appends the parent area name to the name, if called
    """
    parent_id = get_parent_geography_id(centroid)
    if not parent_id:
        return None
    parent = dao_get_area_by_id(parent_id)
    if not parent:
        return None
    name = parent.name
    if name.endswith(", City of"):
        return f"City of {name[:-9]}"
    if name.endswith(", County of"):
        return f"County of {name[:-11]}"


def generate_centroid_for_coordinate_area(first_coordinate, second_coordinate, coordinate_type):
    """Returns a Point geometry for given coordinates, if coordinate_type is easting_northing the
    coordinates will first need to be transformed to the required CRS (EPSG:4326) for latitude, longitude"""
    if coordinate_type == "latitude_longitude":
        centroid = shapely.Point(float(second_coordinate), float(first_coordinate)).wkt
    elif coordinate_type == "easting_northing":
        # Transforms eastings northings to latitude and longitude for centroid query
        transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
        longitude, latitude = transformer.transform(first_coordinate, second_coordinate)
        centroid = shapely.Point(float(longitude), float(latitude)).wkt
    return centroid


def ensure_valid_wkt(wkt):
    """Returns valid WKT for a given WKT string, or error response if area can't be fixed."""
    geom = shapely.wkt.loads(wkt)
    if geom.is_valid:
        return wkt
    fixed_geom = geom.buffer(0)
    if fixed_geom.is_valid:
        return fixed_geom.wkt
    return (
        jsonify({"message": "Combined geometry is invalid"}),
        400,
    )


def bulk_input_error_messages_by_geography_type(type_name):
    """
    Stored error messages for bulk area input by type_name.
    """
    if type_name == "flood_warning_areas":
        return {
            "missing_data": "Enter at least 1 Flood Warning TA code",
            "duplicates": "All Flood Warning TA codes must be unique",
            "invalid": "Flood Warning TA code not found",
            "exceeds_limit": "Maximum of 25 TA codes in an emergency alert",
            "already_selected": "Flood Warning TA code already selected",
        }
    elif type_name == "local_authorities":
        return {
            "missing_data": "Enter at least 1 local authority",
            "duplicates": "All local authorities must be unique",
            "invalid": "Local authority not found",
            "exceeds_limit": "Maximum of 25 local authorities allowed as a list in one emergency alert",
            "already_selected": "Local authority already selected",
        }
    else:
        return {
            "missing_data": "Enter at least 1 area",
            "duplicates": "Area names must be unique",
            "invalid": "Area not found",
            "exceeds_limit": "You can add no more than 25 areas",
            "already_selected": "Area already selected",
        }


def validate_bulk_area_input(area_names, type_name):
    """
    Returns error message, or None, depending on whether list of area names provided is valid or not.
    """
    error_messages = bulk_input_error_messages_by_geography_type(type_name)

    # If no area_names posted
    if not area_names:
        return error_messages["missing_data"]

    # If duplicate area names posted
    if len(area_names) != len(set(area_names)):
        return error_messages["duplicates"]

    # We can't add more than 25 areas at a time for bulk input
    if len(area_names) > 25:
        return error_messages["exceeds_limit"]

    return None


def create_alert_area_dict(ids=None, names=None, polygons=None):
    ids = ids or []
    names = names or []
    polygons = polygons or []

    return {
        "ids": ids,
        "names": names,
        "aggregate_names": names,
        "simple_polygons": polygons,
    }


def get_existing_area_data(message):
    """
    Returns ids, names, and polygons for existing areas for
    either a broadcast_message or template.
    """
    existing_areas = message.areas
    existing_ids = existing_areas.get("ids") or []
    existing_names = existing_areas.get("names") or []
    existing_polygons = existing_areas.get("simple_polygons") or []
    return existing_ids, existing_names, existing_polygons


def build_remaining_area_wkt(existing_ids, area_id_to_remove):
    """Builds the area for the specified `existing_ids`, minus the area to be removed"""
    remaining_ids = [
        area_id
        for area_id in existing_ids
        if area_id != area_id_to_remove
        and (not area_id.startswith("postcodes") and not area_id.startswith("coordinates"))
    ]
    remaining_postcode_ids = [
        area_id for area_id in existing_ids if area_id != area_id_to_remove and area_id.startswith("postcodes")
    ]
    remaining_coordinates_ids = [
        area_id for area_id in existing_ids if area_id != area_id_to_remove and area_id.startswith("coordinates")
    ]

    if not remaining_ids and not remaining_postcode_ids and not remaining_coordinates_ids:
        return [], [], None

    remaining_areas = dao_get_areas_by_ids(set(remaining_ids))

    postcode_areas = []
    coordinate_areas = []

    for postcode_id in remaining_postcode_ids:
        x, y, radius, postcode = parse_postcode_id(postcode_id)
        centroid = shapely.Point(x, y).wkt
        circle_wkt = dao_create_circle_area(centroid, radius)
        postcode_areas.append(circle_wkt)

    for coordinate_id in remaining_coordinates_ids:
        x, y, radius, coordinate_type = parse_coordinate_id(coordinate_id)
        centroid = generate_centroid_for_coordinate_area(x, y, coordinate_type)
        circle_wkt = dao_create_circle_area(centroid, radius)
        coordinate_areas.append(circle_wkt)

    remaining_db_wkts = [to_shape(area.geometry).wkt for area in remaining_areas]
    circle_wkts = postcode_areas + coordinate_areas
    remaining_wkts = remaining_db_wkts + circle_wkts

    remaining_combined_wkt = dao_create_area(remaining_wkts)
    remaining_combined_wkt = ensure_valid_wkt(remaining_combined_wkt)

    polygons = Polygons.from_wkt(remaining_combined_wkt, utm_crs="EPSG:4326")

    new_area_ids = [id for id in existing_ids if id != area_id_to_remove]
    return new_area_ids, polygons.polygons, remaining_ids or remaining_postcode_ids or remaining_coordinates_ids
