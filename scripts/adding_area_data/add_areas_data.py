import os
import uuid
from datetime import datetime, timezone
import pandas as pd

from utils import (
    copy_dataframe_to_table,
    create_db_connection,
    get_source_data,
    insert_data_into_table,
)

VERSION = "1.0.0"
AREAS_SOURCE_BUCKET = os.environ.get("AREAS_SOURCE_BUCKET_NAME")

AREAS = [
    "postcodes",
    "countries",
    "counties_and_unitary_authorities",
    "reppir_sites",
    "test",
    "local_authority_districts",
    "flood_warning_areas",
    "wards",
]

GEOGRAPHY_POLYGON_COLUMNS = [
    "id",
    "name",
    "geometry",
    "parent_geography_id",
    "geography_version_id",
    "geography_type_id",
]


def insert_geography_version(conn, area, geography_type_id):
    # Inserts geography_version row for a given area
    geography_version_id = str(uuid.uuid4())
    insert_data_into_table(
        conn,
        "geography_version",
        ["id", "geography_type_id", "created_at", "version", "source_url", "state"],
        [
            (
                geography_version_id,
                geography_type_id,
                datetime.now(timezone.utc),
                VERSION,
                f"s3://{AREAS_SOURCE_BUCKET}/{VERSION}/{area}.csv",
                "active",
            )
        ],
    )
    return geography_version_id


def insert_geography_type(conn, area):
    # Inserts geography_type row for a given area
    geography_type_id = str(uuid.uuid4())
    insert_data_into_table(
        conn,
        "geography_type",
        ("id", "name", "route"),
        [(geography_type_id, area, area)],
    )
    return geography_type_id


def insert_geography_polygons(conn, area, geography_version_id, geography_type_id):
    # Insert geography_polygons rows for a given area
    data = get_source_data(f"{VERSION}/{area}.csv")
    # Splits CSV into chunks for chunk/batch processing
    csv_data_chunks = pd.read_csv(data, index_col=False, chunksize=100000)
    current_chunk = 1
    for chunk in csv_data_chunks:
        # Adds columns for geography_version_id & geography_type_id, values are generated within this script
        chunk["geography_version_id"] = geography_version_id
        chunk["geography_type_id"] = geography_type_id

        try:
            copy_dataframe_to_table(conn, "geography_polygons", GEOGRAPHY_POLYGON_COLUMNS, chunk)
            print(f"{area} geography_polygons data has been added to the table - chunk #{current_chunk}")
            current_chunk += 1
        except Exception as exc:
            print(f"Could not add {area} data to geography_polygons table: {exc}")


def main():
    # Uses psycopg2 connection to create cursor for database connection
    conn = create_db_connection()

    try:
        for area in AREAS:
            print(f'Processing {area} data')
            # We have 3 tables; geography_type, geography_version, geography_polygons
            # For each area we populate them with relevant data
            geography_type_id = insert_geography_type(conn, area)
            geography_version_id = insert_geography_version(conn, area, geography_type_id)
            insert_geography_polygons(conn, area, geography_version_id, geography_type_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
