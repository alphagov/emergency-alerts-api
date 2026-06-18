import os
import psycopg2
import boto3

s3 = boto3.client("s3")

def get_population_data():
    areas_source_bucket = os.environ.get("AREAS_SOURCE_BUCKET")
    file = s3.get_object(Bucket=areas_source_bucket, Key="population_data.csv")
    return file["Body"]

def get_environment_variables():
    user = os.environ.get("MASTER_USERNAME")
    password = os.environ.get("MASTER_PASSWORD")
    host = os.environ.get("RDS_HOST", "localhost")
    database = os.environ.get("DATABASE", "emergency_alerts")
    return user, password, host, database

def main():
    # Source variables necessary for DB connection
    user, password, host, database = get_environment_variables()

    # Sources population data to be copied
    population_data = get_population_data()

    # Uses psycopg2 connection to create cursor for database connection
    conn = psycopg2.connect(host=host, database=database, user=user, password=password)

    try:
        with conn, conn.cursor() as curr:
            curr.copy_expert(
                """
                COPY populations (id, geometry, density) FROM STDIN WITH CSV HEADER
                """,
                population_data,
            )
        print('Population data has been added to the table')
    except Exception as e:
        print("Could not add data to population table as {}".format(e))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
