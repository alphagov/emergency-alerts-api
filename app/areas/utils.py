import pandas as pd
import shapely

from app.dao.areas_dao import AreasDAO


def split_into_chunks_and_insert_into_db(
    area, geography_version_id, geography_type_id, data, parent_areas, sub_area=False, is_selectable=False
):
    """Used for splitting data for insertion into GeographyPolygons, in batches/chunks"""
    csv_data_chunks = pd.read_csv(data, index_col=False, chunksize=100_000)
    current_chunk = 1
    for chunk in csv_data_chunks:
        try:
            parent_areas = AreasDAO.add_geography_polygons(
                chunk, geography_type_id, geography_version_id, parent_areas, sub_area, is_selectable
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


def convert_lat_long_to_long_lat(existing_polygons):
    # Reverses as utils requires the area polygons to be long, lat NOT lat, long
    existing_polygons_lon_lat = [
        [[longitude, latitude] for latitude, longitude in polygon] for polygon in existing_polygons
    ]
    return existing_polygons_lon_lat


def get_parent_area_name(area_wkt):
    """
    Gets `parent_geography_id`, retrieves the area with this ID
    and then appends the parent area name to the name, if called
    """
    parent_id = AreasDAO.get_dominant_parent_geography_id(area_wkt)
    if not parent_id:
        return None
    parent = AreasDAO.get_area(parent_id)["area"]
    print("parent", parent.name)
    if not parent:
        return None
    name = parent.name
    if name.endswith(", City of"):
        return f"City of {name[:-9]}"
    if name.endswith(", County of"):
        return f"County of {name[:-11]}"
    return name
