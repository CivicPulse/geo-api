#!/bin/bash
set -e

echo "Waiting for database..."
for i in $(seq 1 30); do
  python -c "import psycopg2; psycopg2.connect('$DATABASE_URL_SYNC'.replace('+psycopg2',''))" 2>/dev/null && break
  echo "  attempt $i/30 — retrying in 1s..."
  sleep 1
done

echo "Running Alembic migrations..."
alembic upgrade head

echo "Seeding database..."
python scripts/seed.py

echo "Starting API..."
if [ "${DEBUG:-0}" = "1" ]; then
  echo "Starting API with debugpy on port 5680 (waiting for client)..."
  exec python -m debugpy --listen 0.0.0.0:5680 --wait-for-client -m uvicorn civpulse_geo.main:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn civpulse_geo.main:app --host 0.0.0.0 --port 8000
fi
