import os

import pandas as pd
import psutil

from app.dao.areas_dao import AreasDAO


def mem():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


def split_into_chunks_and_insert_into_db(
    area, geography_version_id, data, parent_areas, sub_area=False, is_selectable=False
):
    """Used for splitting data for insertion into GeographyPolygons, in batches/chunks"""
    csv_data_chunks = pd.read_csv(data, index_col=False, chunksize=50_000)
    current_chunk = 1
    for chunk in csv_data_chunks:
        try:
            parent_areas = AreasDAO.add_geography_polygons(
                chunk, geography_version_id, parent_areas, sub_area, is_selectable
            )
            print(f"parent_areas={len(parent_areas):,} mem={mem():.0f} MB")
            print(f"{area} geography_polygons data has been added to the table - chunk #{current_chunk}")
            current_chunk += 1
        except Exception as e:
            print(f"Could not add {area} data to geography_polygons table: {e}")
            raise e
    return parent_areas
