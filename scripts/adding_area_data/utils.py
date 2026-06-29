import os
import boto3
import psycopg2

s3 = boto3.client("s3")


def get_source_data(filename):
    areas_source_bucket = os.environ.get("AREAS_SOURCE_BUCKET_NAME")
    file = s3.get_object(Bucket=areas_source_bucket, Key=filename)
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


def copy_data_to_table(data, conn, table_name, columns):
    try:
        with conn, conn.cursor() as curr:
            curr.copy_expert(
                f"""
                COPY {table_name} ({",".join(columns)}) FROM STDIN WITH CSV HEADER
                """,
                data,
            )
        print(f"{table_name} data has been added to the table")
    except Exception as e:
        print(f"Could not add data to {table_name} table as {e}")


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