import boto3

from utils import copy_data_to_table, create_db_connection, get_environment_variables, get_source_data

s3 = boto3.client("s3")


def main():
    # Sources population data to be copied
    population_data = get_source_data("population_data.csv")

    # Uses psycopg2 connection to create cursor for database connection
    conn = create_db_connection()
    try:
        copy_data_to_table(data=population_data, conn=conn, table_name="populations", columns=["id", "geometry", "density"])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
