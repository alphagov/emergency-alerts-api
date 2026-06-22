import psycopg2
import boto3

from scripts.adding_area_data.utils import copy_data_to_table, get_environment_variables, get_source_data

s3 = boto3.client("s3")


def main():
    # Source variables necessary for DB connection
    user, password, host, database = get_environment_variables()

    # Sources population data to be copied
    population_data = get_source_data("population_data.csv")

    # Uses psycopg2 connection to create cursor for database connection
    conn = psycopg2.connect(host=host, database=database, user=user, password=password)

    copy_data_to_table(data=population_data, conn=conn, table_name="populations", columns=["id", "geometry", "density"])


if __name__ == "__main__":
    main()
