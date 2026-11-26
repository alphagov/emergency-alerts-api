import shapely
from pyproj import Transformer


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
