import os
import uuid
from io import StringIO

import boto3
import pandas as pd
import psycopg2

s3 = boto3.client("s3")
AREAS_SOURCE_BUCKET = os.environ.get("AREAS_SOURCE_BUCKET_NAME")

GEOGRAPHY_POLYGON_COLUMNS = [
    "id",
    "geographic_id",
    "name",
    "geometry",
    "parent_geography_id",
    "geography_version_id",
    "geography_type_id",
]


def get_source_data(filename):
    file = s3.get_object(Bucket=AREAS_SOURCE_BUCKET, Key=filename)
    return file["Body"]


def get_environment_variables():
    user = os.environ.get("MASTER_USERNAME")
    password = os.environ.get("MASTER_PASSWORD")
    host = os.environ.get("RDS_HOST", "localhost")
    database = os.environ.get("DATABASE", "emergency_alerts")
    return user, password, host, database


def create_db_connection():
    # Create and return a psycopg2 connection, created using environment variables
    user, password, host, database = get_environment_variables()
    return psycopg2.connect(host=host, database=database, user=user, password=password)


def copy_from_stdin(conn, table_name, columns, data):
    # Runs COPY ... FROM STDIN WITH CSV HEADER
    with conn, conn.cursor() as curr:
        curr.copy_expert(
            f"""
            COPY {table_name} ({",".join(columns)})
            FROM STDIN WITH CSV HEADER
            """,
            data,
        )


def copy_data_to_table(data, conn, table_name, columns):
    try:
        copy_from_stdin(conn, table_name, columns, data)
        print(f"{table_name} data has been added to the table")
    except Exception as exc:
        print(f"Could not add data to {table_name} table: {exc}")


def copy_dataframe_to_table(conn, table_name, columns, df):
    # Copy a DataFrame into a table
    sio = StringIO()
    df.to_csv(sio, index=False, columns=columns)
    sio.seek(0)
    copy_from_stdin(conn, table_name, columns, sio)


def insert_data_into_table(conn, table_name, columns, values):
    query = f"""
        INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['%s']*len(columns))})
    """
    try:
        with conn, conn.cursor() as curr:
            curr.executemany(query, values)
        print(f"{table_name} data has been added to the table")
    except Exception as e:
        print(f"Could not add data to {table_name} table as {e}")


def split_into_chunks_and_insert_into_db(conn, area, geography_version_id, geography_type_id, data):
    csv_data_chunks = pd.read_csv(data, index_col=False, chunksize=100000)
    current_chunk = 1
    for chunk in csv_data_chunks:
        # Adds columns for geography_version_id & geography_type_id, values are generated within this script
        chunk["id"] = [uuid.uuid4() for _ in range(len(chunk))]
        chunk["geography_version_id"] = geography_version_id
        chunk["geography_type_id"] = geography_type_id

        try:
            copy_dataframe_to_table(conn, "geography_polygons", GEOGRAPHY_POLYGON_COLUMNS, chunk)
            print(f"{area} geography_polygons data has been added to the table - chunk #{current_chunk}")
            current_chunk += 1
        except Exception as exc:
            print(f"Could not add {area} data to geography_polygons table: {exc}")
