# CivPulse Geo API

Geocoding and address validation service with multi-provider caching and local data source support.

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/framework-FastAPI-009688)
![PostgreSQL/PostGIS](https://img.shields.io/badge/database-PostgreSQL%2FPostGIS-336791)
![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green)

An internal REST API for the CivPulse ecosystem providing geocoding and address validation services to other CivPulse systems (run-api, vote-api, etc.). It acts as a smart caching layer over multiple geocoding providers — both external services and local data sources — storing results to reduce redundant lookups. System administrators can override the official geocoded location for any address when providers disagree.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [CLI Commands](#cli-commands)
- [Data Providers](#data-providers)
- [Development](#development)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [License](#license)

---

## Features

- Multi-provider geocoding with result caching (Census, OpenAddresses, NAD, Tiger/LINE)
- Address validation with USPS-standard normalization via scourgify
- Batch endpoints for both geocoding and validation
- Local data source providers that query local data directly without external API calls
- Admin override for setting the official geocoding record for any address
- Plugin-style provider architecture — new providers can be added without touching core logic
- CLI tools for bulk data import (GeoJSON, KML, SHP, OpenAddresses, NAD, Tiger/LINE)

---

## Tech Stack

| Component       | Technology                      |
|-----------------|---------------------------------|
| Runtime         | Python 3.12                     |
| Framework       | FastAPI                         |
| Database        | PostgreSQL 17 + PostGIS 3.5     |
| ORM             | SQLAlchemy 2.0 + GeoAlchemy2   |
| Async driver    | asyncpg                         |
| HTTP client     | httpx                           |
| Migrations      | Alembic                         |
| CLI             | Typer + Rich                    |
| Package manager | uv                              |
| Dev environment | Docker Compose                  |

---

## Quick Start

**Prerequisites:** Docker, Docker Compose

```bash
# Clone the repository
git clone <repo-url> geo-api
cd geo-api

# Copy environment file
cp .env.example .env

# Start the stack (PostGIS + API, runs migrations and seed automatically)
docker compose up
```

Once the stack is running:

- Health check: http://localhost:8042/health
- Interactive API docs (Swagger UI): http://localhost:8042/docs

---

## API Endpoints

| Method | Path                                  | Description                                   |
|--------|---------------------------------------|-----------------------------------------------|
| POST   | /geocode                              | Geocode a freeform address (cache-first)      |
| POST   | /geocode/batch                        | Batch geocode multiple addresses              |
| PUT    | /geocode/{hash}/official              | Set the official geocoding result (admin)     |
| POST   | /geocode/{hash}/refresh               | Force re-query all providers for an address   |
| GET    | /geocode/{hash}/providers/{name}      | Get a provider-specific geocoding result      |
| POST   | /validate                             | Validate and USPS-standardize an address      |
| POST   | /validate/batch                       | Batch validate multiple addresses             |
| GET    | /health                               | Service health check                          |

### Example: Single geocode request

```bash
curl -X POST http://localhost:8042/geocode \
  -H "Content-Type: application/json" \
  -d '{"address": "123 Main St, Macon, GA 31201"}'
```

---

## CLI Commands

The `geo-import` CLI runs inside the API container and provides bulk data import tools.

| Command                                  | Description                                          |
|------------------------------------------|------------------------------------------------------|
| `geo-import import <file>`               | Import GIS data file (GeoJSON, KML, SHP)             |
| `geo-import load-oa <file.geojson.gz>`   | Load OpenAddresses dataset into local database       |
| `geo-import load-nad <file.zip> --state GA` | Load NAD dataset filtered by state               |
| `geo-import setup-tiger <state>`         | Install Tiger geocoder extensions and state data     |

**Note:** `setup-tiger` must be run inside the `db` container. All other commands run in the `api` container.

```bash
# Import OpenAddresses data for Bibb County, Georgia
docker compose exec api geo-import load-oa data/us_ga_bibb.geojson.gz

# Load NAD data for Georgia
docker compose exec api geo-import load-nad data/NAD_r21.zip --state GA

# Set up Tiger geocoder for Georgia (run in db container)
docker compose exec db geo-import setup-tiger GA
```

**Import ordering:** Run GIS data imports before starting API geocoding for any given address. The
first geocoding result for an address creates the official record; importing GIS data afterward will
not overwrite an existing official record.

---

## Data Providers

The API uses a plugin-style provider architecture. Providers fall into two categories: external
services (results are cached in the database) and local data sources (results are returned directly
without caching).

### External providers

**US Census Geocoder** — Free, no API key required. Calls the Census Bureau's public geocoding API.

### Local providers

Local providers bypass the database cache and return results directly. They require data to be
loaded in advance using the CLI import tools.

| Provider          | Data source                              | Import command     |
|-------------------|------------------------------------------|--------------------|
| OpenAddresses     | Curated address datasets (.geojson.gz)   | `load-oa`          |
| NAD               | National Address Database (.zip)         | `load-nad`         |
| Tiger/LINE        | PostGIS Tiger geocoder extension         | `setup-tiger`      |

**scourgify** is used for offline address validation and USPS-standard normalization. It requires no
data import and works without an internet connection.

---

## Development

### Running locally

```bash
docker compose up
```

The API container mounts `./src` as a volume, so the server auto-reloads on source file changes.
No container rebuild is needed during active development.

### Running tests

```bash
# Inside the container
docker compose exec api pytest

# Locally with uv (requires database connection)
uv run pytest
```

### Debugger (debugpy)

The `DEBUG=1` environment variable is set by default in `docker-compose.yml`. When active, debugpy
listens on port 5680 and the API waits for a debugger to attach before starting.

A VS Code attach configuration is available in `.vscode/launch.json`. Use **"Attach to geo-api
(Docker)"** from the Run and Debug panel.

To disable the debugger wait and run the API immediately, set `DEBUG=0` in `docker-compose.yml`.

---

## Environment Variables

| Variable            | Description                                              | Default        |
|---------------------|----------------------------------------------------------|----------------|
| `DATABASE_URL`      | Async PostgreSQL connection string (asyncpg driver)      | *(see .env.example)* |
| `DATABASE_URL_SYNC` | Sync PostgreSQL connection string (psycopg2, used by Alembic and CLI) | *(see .env.example)* |
| `LOG_LEVEL`         | Logging verbosity (DEBUG, INFO, WARNING, ERROR)          | `DEBUG`        |
| `ENVIRONMENT`       | Runtime environment (`development`, `production`)        | `development`  |
| `DEBUG`             | Enable debugpy remote debugger (`1` to enable)           | `1` in compose |

Copy `.env.example` to `.env` for local development. The example values are pre-configured for the
Docker Compose setup.

---

## Project Structure

```
src/civpulse_geo/
  api/           # FastAPI route handlers (geocoding, validation, health)
  cli/           # Typer CLI commands (geo-import)
  models/        # SQLAlchemy ORM models
  providers/     # Geocoding and validation provider plugins
  schemas/       # Pydantic request/response schemas
  services/      # Business logic layer (pipeline, caching, dispatch)
  config.py      # Pydantic settings (reads from environment)
  database.py    # Database session and engine management
  main.py        # FastAPI application entrypoint and lifespan
```

---

## License

AGPL-3.0 — see [LICENSE](LICENSE) file.
