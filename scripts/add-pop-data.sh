#!/bin/bash
set -e

# POSTGRES_USER will need to be set before running script, otherwise remains as default value
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DATABASE" -h "$RDS_HOST" -p "$RDS_PORT" <<-EOSQL
	\COPY populations (id, geometry, density) FROM './scripts/population_data.csv' CSV HEADER;
EOSQL
