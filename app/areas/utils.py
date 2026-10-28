import pandas as pd
import shapely
from pyproj import Transformer

from app.dao.areas_dao import AreasDAO


def split_into_chunks_and_insert_into_db(
    area, geography_version_id, data, parent_areas, sub_area=False, is_selectable=False
):
    """Used for splitting data for insertion into GeographyPolygons, in batches/chunks"""
    csv_data_chunks = pd.read_csv(data, index_col=False, chunksize=100_000)
    current_chunk = 1
    for chunk in csv_data_chunks:
        try:
            parent_areas = AreasDAO.add_geography_polygons(
                chunk, geography_version_id, parent_areas, sub_area, is_selectable
            )
            print(f"{area} geography_polygons data has been added to the table - chunk #{current_chunk}")
            current_chunk += 1
        except Exception as e:
            print(f"Could not add {area} data to geography_polygons table: {e}")
            raise e
    return parent_areas


def wkt_geometry_to_alert_polygons(area_wkt):
    remaining_geometry = shapely.wkt.loads(area_wkt)
    if remaining_geometry.geom_type == "Polygon":
        remaining_polygons = [remaining_geometry.exterior.coords]
    elif remaining_geometry.geom_type == "MultiPolygon":
        remaining_polygons = [polygon.exterior.coords for polygon in remaining_geometry.geoms]
    else:
        remaining_polygons = []

    return [[[coordinate[1], coordinate[0]] for coordinate in polygon] for polygon in remaining_polygons]


def reorder_polygons_to_long_lat(existing_polygons):
    # Reverses as utils requires the area polygons to be long, lat NOT lat, long
    existing_polygons_lon_lat = [
        [[longitude, latitude] for latitude, longitude in polygon] for polygon in existing_polygons
    ]
    return existing_polygons_lon_lat


def convert_to_long_lat_coordinates(first_coordinate, second_coordinate, coordinate_type):
    """Transforms eastings, northings coordinates from British National Grid
    (EPSG:27700) to WGS84 (EPSG:4326). Coordinates supplied as
    latitude/longitude are just reordered"""
    try:
        if coordinate_type == "easting_northing":
            # Transform coordinates from eastings northings to lat long
            # always_xy=True ensures the transformer
            # receives and returns coordinates in correct order
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
            # If coordinate_id hasn't been split correctly
            raise ValueError(f"Unsupported coordinate type: {coordinate_type}")
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid coordinate values or coordinate type") from error
    return longitude, latitude


def get_parent_area_name(area_wkt):
    """
    Gets `parent_geography_id`, retrieves the area with this ID
    and then appends the parent area name to the name, if called
    """
    parent_id = AreasDAO.get_dominant_parent_geography_id(area_wkt)
    if not parent_id:
        return None
    parent = AreasDAO.get_area(parent_id)["area"]
    if not parent:
        return None
    name = parent.name
    if name.endswith(", City of"):
        return f"City of {name[:-9]}"
    if name.endswith(", County of"):
        return f"County of {name[:-11]}"
    return name


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
