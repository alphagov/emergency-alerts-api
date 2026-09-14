import os
import uuid
from datetime import datetime, timezone

from utils import (
    create_db_connection,
    get_source_data,
    insert_data_into_table,
    split_into_chunks_and_insert_into_db,
)

VERSION = "1.0.0"
AREAS_SOURCE_BUCKET = os.environ.get("AREAS_SOURCE_BUCKET_NAME")

AREAS = {
    "postcodes": {"display_name": "Postcode areas", "name_singular": "postcode area"},
    "countries": {"display_name": "Countries", "name_singular": "country"},
    "reppir_sites": {"display_name": "REPPIR DEPZ sites", "name_singular": "REPPIR DEPZ site"},
    "test": {"display_name": "Test areas", "name_singular": "test area"},
    "flood_warning_areas": {
        "display_name": "Flood Warning Target Areas (TA code)",
        "name_singular": "Flood Warning Target Area",
    },
    "wards": {"display_name": "Wards", "name_singular": "ward"},
    "local_authorities": {
        "display_name": "Local authorities",
        "name_singular": "local authority",
    },
}


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
    geography_name = AREAS[area]["display_name"]
    name_singular = AREAS[area]["name_singular"]
    insert_data_into_table(
        conn,
        "geography_type",
        ("id", "name", "route", "name_singular"),
        [(geography_type_id, geography_name, area, name_singular)],
    )
    return geography_type_id


def insert_geography_polygons(conn, area, geography_version_id, geography_type_id):
    # Insert geography_polygons rows for a given area
    if area == "local_authorities":
        # If the area is local_authorities, these are made up of counties_and_unitary_authorities
        # and local_authority_districts
        for sub_area in ["counties_and_unitary_authorities", "local_authority_districts"]:
            data = get_source_data(f"{VERSION}/{sub_area}.csv")
            # Splits CSV into chunks for chunk/batch processing
            split_into_chunks_and_insert_into_db(conn, area, geography_version_id, geography_type_id, data)
    else:
        data = get_source_data(f"{VERSION}/{area}.csv")
        # Splits CSV into chunks for chunk/batch processing
        split_into_chunks_and_insert_into_db(conn, area, geography_version_id, geography_type_id, data)


def main():
    # Uses psycopg2 connection to create cursor for database connection
    conn = create_db_connection()

    try:
        for area in AREAS:
            print(f"Processing {area} data")
            # We have 3 tables; geography_type, geography_version, geography_polygons
            # For each area we populate them with relevant data
            geography_type_id = insert_geography_type(conn, area)
            geography_version_id = insert_geography_version(conn, area, geography_type_id)
            insert_geography_polygons(conn, area, geography_version_id, geography_type_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
