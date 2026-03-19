#!/bin/bash
set -e

echo "Running Alembic migrations..."
alembic upgrade head

echo "Seeding database..."
python scripts/seed.py

echo "Starting API..."
exec uvicorn civpulse_geo.main:app --host 0.0.0.0 --port 8000
