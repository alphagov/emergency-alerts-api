import uuid

import shapely
from emergency_alerts_utils.formatters import formatted_list
from emergency_alerts_utils.polygons import Polygons
from flask import Blueprint, jsonify, request
from geoalchemy2.shape import to_shape
from pyproj import Transformer

from app.areas.utils import (
    convert_lat_long_to_long_lat,
    get_parent_area_name,
    wkt_geometry_to_alert_polygons,
)
from app.dao.areas_dao import AreasDAO
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
from app.schemas import (
    template_schema,
)

areas_blueprint = Blueprint(
    "areas",
    __name__,
    url_prefix="/areas",
)


@areas_blueprint.route("/<area_id>", methods=["GET"])
def get_area_by_id(area_id):
    area_data = AreasDAO.get_area(area_id)

    if area_data is None:
        return jsonify({"message": "Area not found"}), 404

    area = area_data["area"]

    return jsonify(
        {
            "data": {
                **area.serialize(),
                "geography_type_name": area_data["geography_type_name"],
            }
        }
    )


@areas_blueprint.route("/get-areas", methods=["POST"])
def get_areas_by_ids():
    data = request.get_json() or {}
    area_ids = data.get("area_ids") or []
    predefined_area_ids = []
    postcode_ids = []  # Postcode and Coordinate areas that we generate ourselves, from IDs
    coordinate_ids = []
    for area_id in area_ids:
        if area_id.startswith("postcodes"):
            postcode_ids.append(area_id)
        elif area_id.startswith("coordinates"):
            coordinate_ids.append(area_id)
        else:
            # If not postcode, coordinate areas or legacy, then
            # we assume it is an area we have predefined in geography_polygona
            predefined_area_ids.append(area_id)

    data = []
    areas = AreasDAO.get_areas_by_ids(set(predefined_area_ids))
    areas_serialized = [
        {
            **area_data["area"].serialize(),
            "geography_type_name": area_data["geography_type_name"],
        }
        for area_data in areas
    ]
    for postcode_id in postcode_ids:
        # "postcodes_{centroid.x}_{centroid.y}_{radius}_{postcode}"
        # Shapely stores Point coordinates as x=longitude, y=latitude.
        _, x_coordinate, y_coordinate, radius, postcode = postcode_id.split("_", 4)
        radius = float(radius)
        x_coordinate = float(x_coordinate)
        y_coordinate = float(y_coordinate)
        centroid = shapely.Point(x_coordinate, y_coordinate).wkt
        name = f"{radius:g}km around the postcode {postcode}"
        parent_area = get_parent_area_name(centroid)
        if parent_area:
            name = f"{name}, in {parent_area}"

        areas_serialized.append(
            {
                "id": postcode_id,
                "name": name,
                "geographic_id": postcode,
                # "geography_type": "postcodes",
                "geography_type_name": "postcodes",
            }
        )
    for coordinate_id in coordinate_ids:
        _, first_coordinate, second_coordinate, radius, coordinate_type = coordinate_id.split("_", 4)
        radius = float(radius)
        first_coordinate = float(first_coordinate)
        second_coordinate = float(second_coordinate)

        if coordinate_type == "latitude_longitude":
            latitude = first_coordinate
            longitude = second_coordinate
            name = f"{radius:g}km around {latitude:g} latitude, {longitude:g} longitude"
        elif coordinate_type == "easting_northing":
            transformer = Transformer.from_crs(
                "EPSG:27700",
                "EPSG:4326",
                always_xy=True,
            )
            longitude, latitude = transformer.transform(
                first_coordinate,
                second_coordinate,
            )
            name = (
                f"{radius:g}km around the easting of {first_coordinate:g} " f"and the northing of {second_coordinate:g}"
            )

        centroid = shapely.Point(longitude, latitude).wkt
        parent_area = get_parent_area_name(centroid)
        if parent_area:
            name = f"{name}, in {parent_area}"
        areas_serialized.append(
            {"id": coordinate_id, "name": name, "geographic_id": None, "geography_type_name": "coordinates"}
        )

    return jsonify({"data": areas_serialized})


@areas_blueprint.route("/get-local-authorities-by-names", methods=["POST"])
def get_local_authorities_areas_by_names():
    data = request.get_json() or {}
    area_names = data.get("area_names")
    areas = AreasDAO.get_areas_by_names(area_names, "local_authorities")
    found_by_name = {area.name: area.id for area in areas}

    # Returns 400 error for a missing name - error to then be
    # rendered as is in Admin application
    for name in area_names:
        if name not in found_by_name:
            message = f"Local authority '{name}' not found"
            return jsonify({"message": message}), 400

    ids = [found_by_name[name] for name in area_names]
    return jsonify({"data": ids})


@areas_blueprint.route("/get-flood-warning-areas-by-geographic-ids", methods=["POST"])
def get_flood_warning_areas_by_geographic_ids():
    data = request.get_json() or {}
    geographic_ids = data.get("ta_codes") or []

    areas = AreasDAO.get_areas_by_geographic_ids(
        geographic_ids,
        "flood_warning_areas",
    )

    found_by_geographic_id = {area.geographic_id: area.id for area in areas}

    # Return 400 for a geographic ID that could not be found. This error is
    # rendered as-is by the Admin application.
    for geographic_id in geographic_ids:
        if geographic_id not in found_by_geographic_id:
            message = f"Flood Warning TA Code '{geographic_id}' not found"
            return jsonify({"message": message}), 400

    area_ids = [found_by_geographic_id[geographic_id] for geographic_id in geographic_ids]
    return jsonify({"data": area_ids})


@areas_blueprint.route("/geography-types", methods=["GET"])
def get_geography_types():
    """Returns a list of geography types/libraries."""
    results = AreasDAO.get_geography_types()
    local_authority_routes = ["counties_and_unitary_authorities", "local_authority_districts"]
    geography_types = []

    # Combine county and unitary authorities and local authority districts
    for version_id, geography_type in results:
        if geography_type.route not in local_authority_routes:
            geography_types.append(
                {
                    "id": str(geography_type.id),
                    "name": geography_type.name,
                    "name_singular": geography_type.name_singular,
                    "route": geography_type.route,
                    "version_id": version_id,
                }
            )

    # Adds local authorities type
    geography_types.append(
        {
            "id": str(uuid.uuid4()),
            "name": "Local Authorities",
            "name_singular": "local authority",
            "route": "local_authorities",
            "version_id": "local_authorities",
        }
    )
    # Adds coordinates type
    geography_types.append(
        {
            "id": "coordinates",
            "name": "Coordinates",
            "name_singular": "Coordinates",
            "examples": [],
            "route": "coordinates",
            "areas": [],
        }
    )
    return jsonify({"data": geography_types})


@areas_blueprint.route("/geography-types/<type_route>/examples", methods=["GET"])
def get_geography_type_examples(type_route):
    """Returns the example hint text for a geography type/library."""
    data = AreasDAO.get_geography_type_examples(type_route)
    count = data["count"]
    example_areas = data["examples"]

    # Generates examples string to be displayed on Admin
    # applications 'libraries' page
    if count <= 4:
        examples = formatted_list(example_areas, before_each="", after_each="")
    else:
        shown = example_areas[:3]
        remaining = count - 3
        examples = f"{', '.join(shown)} and {remaining} more..."

    return jsonify({"data": examples})


@areas_blueprint.route("/geography-types/<version_id>/areas", methods=["GET"])
@areas_blueprint.route("/geography-types/<version_id>/<parent_id>/areas", methods=["GET"])
def get_areas(version_id, parent_id=None):
    data = AreasDAO.get_areas(version_id, parent_id)
    areas = []
    for area in data:
        areas.append(area.serialize())
    return jsonify({"data": areas})


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/add-areas", methods=["POST"])
def add_areas(service_id, message_id, message_type):
    data = request.get_json() or {}
    area_ids = data.get("area_ids") or []
    version_id = data.get("version_id")
    areas = AreasDAO.get_areas_by_ids(set(area_ids), version_id)

    if message_type == "broadcast":
        message = dao_get_broadcast_message_by_id_and_service_id(message_id, service_id)
    elif message_type == "templates":
        message = dao_get_template_by_id_and_service_id(message_id, service_id)
    else:
        return jsonify({"message": "Unsupported message type"}), 400

    message_areas = message.areas or {}
    existing_ids = message_areas.get("ids", [])
    existing_names = message_areas.get("names", [])
    area_wkts = []
    names = []
    for area in areas:
        area_wkts.append(to_shape(area["area"].geometry).wkt)
        names.append(area["area"].name)

    if message_areas:
        polygons = convert_lat_long_to_long_lat(message_areas["simple_polygons"])
        area_wkts.append(Polygons(polygons=polygons).as_wkt)

    combined_wkt = AreasDAO.create_area(area_wkts)
    message.areas = {
        "ids": area_ids + existing_ids,
        "names": names + existing_names,
        "aggregate_names": names + existing_names,
        "simple_polygons": wkt_geometry_to_alert_polygons(combined_wkt),
    }

    dao_save_object(message)

    if message_type == "broadcast":
        dao_create_broadcast_message_version(
            message,
            service_id,
            message.updated_by_id,
        )
        return jsonify(message.serialize()), 200
    else:
        current_data = dict(template_schema.dump(message).items())
        current_data["areas"] = message.areas

        update_dict = template_schema.load(current_data)
        if update_dict.archived:
            update_dict.folder = None

        dao_update_template(update_dict)
        return jsonify(template_schema.dump(update_dict)), 200


@areas_blueprint.route("/check-coordinates-valid", methods=["POST"])
def check_coordinates_valid():
    """Returns boolean result of whether or not the specified
    coordinates lie within UK polygon area"""
    data = request.get_json()
    first = data.get("first_coordinate")
    second = data.get("second_coordinate")
    coordinate_type = data.get("coordinate_type")
    valid = AreasDAO.check_coordinates_valid(first, second, coordinate_type)
    return jsonify(
        {
            "data": valid,
        }
    )


@areas_blueprint.route("/coordinate-area", methods=["POST"])
def create_coordinate_area():
    """Returns WKT string of created coordinate area, created using radius and
    centroid, formed from specified coordinates"""
    data = request.get_json()
    first_coordinate = float(data.get("first_coordinate"))
    second_coordinate = float(data.get("second_coordinate"))
    coordinate_type = data.get("coordinate_type")
    radius = float(data.get("radius"))

    if not AreasDAO.check_coordinates_valid(first_coordinate, second_coordinate, coordinate_type):
        return jsonify({"message": "Enter coordinates within the UK"}), 400

    if coordinate_type == "easting_northing":
        # Convert British National Grid easting/northing to
        # longitude/latitude. always_xy=True ensures the transformer
        # receives and returns coordinates in x/y order.
        transformer = Transformer.from_crs(
            "EPSG:27700",
            "EPSG:4326",
            always_xy=True,
        )
        longitude, latitude = transformer.transform(
            first_coordinate,
            second_coordinate,
        )
    elif coordinate_type == "latitude_longitude":
        latitude = first_coordinate
        longitude = second_coordinate

    centroid = shapely.Point(longitude, latitude).wkt

    circle = AreasDAO.create_circle_area(centroid, radius)
    return jsonify(
        {
            "data": circle,
        }
    )


@areas_blueprint.route("/coordinates/get-centroid", methods=["POST"])
def get_coordinates_centroid():
    """
    Returns a centroid WKT for the provided coordinates, in latitude longitude.
    """
    data = request.get_json() or {}
    first_coordinate = data.get("first_coordinate")
    second_coordinate = data.get("second_coordinate")
    coordinate_type = data.get("coordinate_type")

    if not AreasDAO.check_coordinates_valid(first_coordinate, second_coordinate, coordinate_type):
        return jsonify({"message": "Enter coordinates within the UK"}), 400

    if coordinate_type == "easting_northing":
        transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
        longitude, latitude = transformer.transform(first_coordinate, second_coordinate)
    else:
        latitude, longitude = first_coordinate, second_coordinate

    centroid = shapely.Point(longitude, latitude).wkt
    return jsonify({"data": centroid})


@areas_blueprint.route("/postcodes/get-centroid", methods=["POST"])
def get_postcode_centroid():
    """
    Returns the centroid WKT for the specific postcode.
    """
    data = request.get_json() or {}
    postcode = data.get("postcode")

    postcode_area = AreasDAO.get_area_by_geographic_id_and_type_route(postcode, "postcodes")
    if not postcode_area:
        return jsonify({"message": "Enter a postcode within the UK"}), 400

    centroid = to_shape(postcode_area.geometry).centroid.wkt
    if centroid is None:
        return jsonify({"message": "Area has no geometry"}), 400

    return jsonify({"data": centroid})


@areas_blueprint.route("/postcode-area", methods=["POST"])
def create_postcode_area():
    """Returns WKT string of created postcode area, created using radius and
    centroid of the latest polygon for the specified postcode boundary"""
    data = request.get_json() or {}
    radius = data.get("radius")
    postcode = data.get("postcode")

    if radius is None or not postcode:
        return jsonify({"message": "Enter postcode and radius to create postcode area"}), 400

    postcode_area = AreasDAO.get_area_by_geographic_id_and_type_route(
        postcode,
        "postcodes",
    )
    if not postcode_area:
        return jsonify({"message": "Enter a postcode within the UK"}), 400

    centroid = to_shape(postcode_area.geometry).centroid
    centroid_wkt = centroid.wkt
    circle = AreasDAO.create_circle_area(centroid_wkt, radius)
    area_id = f"postcodes_{centroid.x}_{centroid.y}_{radius}_{postcode}"

    return jsonify({"circle": circle, "id": area_id})


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/add-postcodes-area", methods=["POST"])
def add_postcode_areas(service_id, message_id, message_type):
    data = request.get_json() or {}
    postcode = data.get("postcode")
    radius = data.get("radius")

    postcode_area = AreasDAO.get_area_by_geographic_id_and_type_route(
        postcode,
        "postcodes",
    )
    centroid = to_shape(postcode_area.geometry).centroid
    circle = AreasDAO.create_circle_area(centroid.wkt, radius)
    area_id = f"postcodes_{centroid.x}_{centroid.y}_{radius}_{postcode}"

    if message_type == "broadcast":
        message = dao_get_broadcast_message_by_id_and_service_id(message_id, service_id)
    elif message_type == "templates":
        message = dao_get_template_by_id_and_service_id(message_id, service_id)
    else:
        return jsonify({"message": "Unsupported message type"}), 400

    message_areas = message.areas or {}
    existing_ids = message_areas.get("ids", [])
    existing_names = message_areas.get("names", [])

    if message_areas:
        polygons = convert_lat_long_to_long_lat(message_areas["simple_polygons"])
        existing_area_wkt = Polygons(polygons=polygons).as_wkt
        combined_wkt = AreasDAO.create_area([circle, existing_area_wkt])
        alert_polygons = wkt_geometry_to_alert_polygons(combined_wkt)
    else:
        alert_polygons = wkt_geometry_to_alert_polygons(circle)

    name = f"{radius:g}km around the postcode {postcode}"
    parent_area = get_parent_area_name(centroid.wkt)
    if parent_area:
        name = f"{name}, in {parent_area}"

    message.areas = {
        "ids": [area_id] + existing_ids,
        "names": [name] + existing_names,
        "aggregate_names": [name] + existing_names,
        "simple_polygons": alert_polygons,
    }

    dao_save_object(message)

    if message_type == "broadcast":
        dao_create_broadcast_message_version(
            message,
            service_id,
            message.updated_by_id,
        )
        return jsonify(message.serialize()), 200
    else:
        current_data = dict(template_schema.dump(message).items())
        current_data["areas"] = message.areas

        update_dict = template_schema.load(current_data)
        if update_dict.archived:
            update_dict.folder = None

        dao_update_template(update_dict)
        return jsonify(template_schema.dump(update_dict)), 200


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/add-coordinates-area", methods=["POST"])
def add_coordinate_areas(service_id, message_id, message_type):
    data = request.get_json() or {}
    first_coordinate = data.get("first_coordinate")
    second_coordinate = data.get("second_coordinate")
    coordinate_type = data.get("coordinate_type")
    radius = data.get("radius")

    # We create coordinate area first
    if coordinate_type == "easting_northing":
        transformer = Transformer.from_crs(
            "EPSG:27700",
            "EPSG:4326",
            always_xy=True,
        )
        longitude, latitude = transformer.transform(
            first_coordinate,
            second_coordinate,
        )
    elif coordinate_type == "latitude_longitude":
        latitude = first_coordinate
        longitude = second_coordinate

    centroid = shapely.Point(longitude, latitude).wkt
    circle = AreasDAO.create_circle_area(centroid, radius)

    if coordinate_type == "latitude_longitude":
        name = f"{radius:g}km around {first_coordinate:g} latitude, {second_coordinate:g} longitude"
    elif coordinate_type == "easting_northing":
        name = f"{radius:g}km around the easting of {first_coordinate:g} and the northing of {second_coordinate:g}"

    parent_area = get_parent_area_name(centroid)
    if parent_area:
        name = f"{name}, in {parent_area}"

    area_id = f"coordinates_{first_coordinate}_{second_coordinate}_{radius}_{coordinate_type}"

    if message_type == "broadcast":
        message = dao_get_broadcast_message_by_id_and_service_id(message_id, service_id)
    elif message_type == "templates":
        message = dao_get_template_by_id_and_service_id(message_id, service_id)
    else:
        return jsonify({"message": "Unsupported message type"}), 400

    message_areas = message.areas or {}
    if message_areas:
        # Polygons need to be reversed because they are stored as lat, long
        polygons = convert_lat_long_to_long_lat(message_areas.get("simple_polygons"))
        message_areas_wkt = Polygons(polygons=polygons).as_wkt
        combined_wkt = AreasDAO.create_area([circle, message_areas_wkt])
        alert_polygons = wkt_geometry_to_alert_polygons(combined_wkt)
    else:
        # Create alert area from circle wkt
        alert_polygons = wkt_geometry_to_alert_polygons(circle)

    message.areas = {
        "ids": [area_id] + message_areas.get("ids", []),
        "names": [name] + message_areas.get("names", []),
        "aggregate_names": [name] + message_areas.get("names", []),
        "simple_polygons": alert_polygons,
    }

    dao_save_object(message)

    if message_type == "broadcast":
        dao_create_broadcast_message_version(
            message,
            service_id,
            message.updated_by_id,
        )
        return jsonify(message.serialize()), 200
    else:
        current_data = dict(template_schema.dump(message).items())
        current_data["areas"] = message.areas

        update_dict = template_schema.load(current_data)
        if update_dict.archived:
            update_dict.folder = None

        dao_update_template(update_dict)
        return jsonify(template_schema.dump(update_dict)), 200


@areas_blueprint.route("/<service_id>/<message_id>/<message_type>/remove-area", methods=["POST"])
def remove_area(service_id, message_id, message_type):
    data = request.get_json() or {}
    area_id_to_remove = data.get("area_id")

    if not area_id_to_remove:
        return jsonify({"message": "area_id is required"}), 400

    if message_type == "broadcast":
        message = dao_get_broadcast_message_by_id_and_service_id(
            message_id,
            service_id,
        )
    elif message_type == "templates":
        message = dao_get_template_by_id_and_service_id(
            message_id,
            service_id,
        )
    else:
        return jsonify({"message": "Unsupported message type"}), 400

    message_areas = message.areas or {}
    existing_ids = list(message_areas.get("ids") or [])
    existing_names = list(message_areas.get("names") or [])

    if area_id_to_remove not in existing_ids:
        return jsonify(message.serialize()), 200

    remaining_ids = [area_id for area_id in existing_ids if area_id != area_id_to_remove]
    names = [name for id, name in zip(existing_ids, existing_names) if id != area_id_to_remove]

    postcode_ids = []
    coordinate_ids = []
    predefined_area_ids = []

    for area_id in remaining_ids:
        if area_id.startswith("postcodes"):
            postcode_ids.append(area_id)
        elif area_id.startswith("coordinates"):
            coordinate_ids.append(area_id)
        else:
            predefined_area_ids.append(area_id)

    remaining_wkts = []
    predefined_areas = AreasDAO.get_areas_by_ids(set(predefined_area_ids))
    for area in predefined_areas:
        remaining_wkts.append(to_shape(area["area"].geometry).wkt)

    for postcode_id in postcode_ids:
        try:
            _, _, _, radius, postcode = postcode_id.split("_", 4)
            radius = float(radius)
        except (TypeError, ValueError):
            return jsonify({"message": "Invalid postcode area ID"}), 400

        postcode_area = AreasDAO.get_area_by_geographic_id_and_type_route(
            postcode,
            "postcodes",
        )
        if not postcode_area:
            return jsonify({"message": "Postcode area not found"}), 404

        centroid = to_shape(postcode_area.geometry).centroid
        remaining_wkts.append(AreasDAO.create_circle_area(centroid.wkt, radius))

    for coordinate_id in coordinate_ids:
        try:
            _, first_coordinate, second_coordinate, radius, coordinate_type = coordinate_id.split("_", 4)
            first_coordinate = float(first_coordinate)
            second_coordinate = float(second_coordinate)
            radius = float(radius)
        except (TypeError, ValueError):
            return jsonify({"message": "Invalid coordinate area ID"}), 400

        if coordinate_type == "easting_northing":
            transformer = Transformer.from_crs(
                "EPSG:27700",
                "EPSG:4326",
                always_xy=True,
            )
            longitude, latitude = transformer.transform(
                first_coordinate,
                second_coordinate,
            )
        elif coordinate_type == "latitude_longitude":
            latitude = first_coordinate
            longitude = second_coordinate
        else:
            return jsonify({"message": "Invalid coordinate type"}), 400

        centroid = shapely.Point(longitude, latitude).wkt
        remaining_wkts.append(AreasDAO.create_circle_area(centroid, radius))

    if remaining_wkts:
        # Combine all of the area WKTs
        remaining_wkt = AreasDAO.create_area(remaining_wkts)
        remaining_polygons = wkt_geometry_to_alert_polygons(remaining_wkt)
    else:
        remaining_polygons = []

    message.areas = {
        **message_areas,
        "ids": remaining_ids,
        "names": names,
        "aggregate_names": names,
        "simple_polygons": remaining_polygons,
    }

    if message_type == "broadcast":
        dao_create_broadcast_message_version(
            message,
            service_id,
            message.updated_by_id,
        )
        return jsonify(message.serialize()), 200
    else:
        current_data = dict(template_schema.dump(message).items())
        current_data["areas"] = message.areas

        update_dict = template_schema.load(current_data)
        if update_dict.archived:
            update_dict.folder = None

        dao_update_template(update_dict)
        return jsonify(template_schema.dump(update_dict)), 200
