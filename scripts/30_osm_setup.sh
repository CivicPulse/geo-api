#!/bin/bash
# Install PostGIS, hstore, and postgis_topology extensions on osm-postgres.
# This script runs via /docker-entrypoint-initdb.d/ during PostgreSQL initdb
# on first startup of the osm-postgres container only.
#
# Phase 24 — creates extensions on the `nominatim` database.
# Mirrors the pattern from scripts/20_tiger_setup.sh.
#
# To re-run after modifying this script, destroy the volume:
#   docker compose --profile osm down -v && docker compose --profile osm up -d osm-postgres
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS hstore;
    CREATE EXTENSION IF NOT EXISTS postgis_topology;
EOSQL

echo "OSM PostgreSQL extensions installed on database $POSTGRES_DB."
