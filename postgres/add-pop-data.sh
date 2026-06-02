#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -h "$RDS_HOST" -p "$RDS_PORT" <<-EOSQL
	\COPY populations (id, geometry, density) FROM './postgres/population_data.csv' CSV HEADER;
EOSQL
