import os
import boto3

s3 = boto3.client("s3")


def get_population_data():
    areas_source_bucket = os.environ.get("AREAS_SOURCE_BUCKET_NAME")
    file = s3.get_object(Bucket=areas_source_bucket, Key="population_data.csv")
    return file["Body"]


def get_environment_variables():
    user = os.environ.get("MASTER_USERNAME")
    password = os.environ.get("MASTER_PASSWORD")
    host = os.environ.get("RDS_HOST", "localhost")
    database = os.environ.get("DATABASE", "emergency_alerts")
    return user, password, host, database


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
    finally:
        conn.close()