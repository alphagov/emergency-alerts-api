import pandas as pd

from app.dao.areas_dao import AreasDAO


def split_into_chunks_and_insert_into_db(
    area, geography_version_id, geography_type_id, data, parent_areas, sub_area=False
):
    """Used for splitting data for insertion into GeographyPolygons, in batches/chunks"""
    csv_data_chunks = pd.read_csv(data, index_col=False, chunksize=100_000)
    current_chunk = 1
    for chunk in csv_data_chunks:
        try:
            parent_areas = AreasDAO.add_geography_polygons(
                chunk, geography_type_id, geography_version_id, parent_areas, sub_area
            )
            print(f"{area} geography_polygons data has been added to the table - chunk #{current_chunk}")
            current_chunk += 1
        except Exception as e:
            print(f"Could not add {area} data to geography_polygons table: {e}")
            raise e
    return parent_areas
