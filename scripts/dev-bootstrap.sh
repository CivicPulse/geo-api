#!/bin/bash
# dev-bootstrap.sh — One-command local data bootstrap for civpulse geo-api dev environment
# Starts all containers, loads all 5 provider datasets, verifies all providers register.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

echo "=== Starting civpulse geo-api dev environment ==="

# Step 1: Build and start containers
echo "--- Building and starting containers..."
docker compose up -d --build

# Step 2: Wait for api to be healthy (max 120s)
echo "--- Waiting for api container to be healthy (max 120s)..."
for i in $(seq 1 24); do
  STATUS=$(docker compose ps api --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health',''))" 2>/dev/null || echo "")
  if [ "$STATUS" = "healthy" ]; then
    echo "    API is healthy."
    break
  fi
  # Fallback: try curl
  if curl -sf http://localhost:8042/health >/dev/null 2>&1; then
    echo "    API health endpoint responding."
    break
  fi
  if [ $i -eq 24 ]; then
    echo "ERROR: API did not become healthy within 120s"
    docker compose logs api --tail 50
    exit 1
  fi
  echo "    attempt $i/24 — retrying in 5s..."
  sleep 5
done

# Step 3: Load OpenAddresses data
echo "--- Loading OpenAddresses data (Bibb County GA)..."
docker compose exec api geo-import load-oa /app/data/US_GA_Bibb_Addresses_2026-03-20.geojson.gz

# Step 4: Load Tiger data (uses mounted tiger-data/ at /gisdata)
echo "--- Loading Tiger/Line data for GA (this may take 10-30 minutes)..."
docker compose exec api geo-import setup-tiger GA

# Step 5: Load NAD data
echo "--- Loading National Address Database data for GA..."
docker compose exec api geo-import load-nad /app/data/NAD_r21_TXT.zip --state GA

# Step 6: Load Macon-Bibb data
echo "--- Loading Macon-Bibb County address points..."
docker compose exec api geo-import load-macon-bibb /app/data/Address_Points.geojson

# Step 7: Restart api so lifespan re-checks all data availability
echo "--- Restarting api to re-check provider data availability..."
docker compose restart api

# Step 8: Wait for api to be healthy again (max 60s)
echo "--- Waiting for api to come back healthy (max 60s)..."
for i in $(seq 1 12); do
  if curl -sf http://localhost:8042/health >/dev/null 2>&1; then
    echo "    API is healthy."
    break
  fi
  if [ $i -eq 12 ]; then
    echo "ERROR: API did not come back healthy within 60s"
    docker compose logs api --tail 50
    exit 1
  fi
  echo "    attempt $i/12 — retrying in 5s..."
  sleep 5
done

# Step 9: Final health check
echo "--- Final health check:"
curl -s http://localhost:8042/health | python3 -m json.tool

echo ""
echo "=== Bootstrap complete! ==="
echo "All 5 providers should now be registered."
echo "Run: docker compose logs api 2>&1 | grep provider"
echo "API available at: http://localhost:8042"
