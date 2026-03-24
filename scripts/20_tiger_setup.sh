#!/bin/bash
# Install PostGIS Tiger geocoder extensions on first container startup.
# This script runs via /docker-entrypoint-initdb.d/ during PostgreSQL initdb.
#
# Extensions only — Tiger/Line data must be loaded separately:
#   docker compose exec db geo-import setup-tiger 13
#
# To re-run after modifying this script, destroy the volume:
#   docker compose down -v && docker compose up -d
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
    CREATE EXTENSION IF NOT EXISTS address_standardizer;
    CREATE EXTENSION IF NOT EXISTS address_standardizer_data_us;
    CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
EOSQL

echo "Tiger geocoder extensions installed."
