FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# System build-time deps (GDAL headers required by fiona at compile time)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgdal-dev libexpat1-dev && \
    rm -rf /var/lib/apt/lists/*

# Dependency layer (cached unless lock file changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy source and install project non-editable (embeds package in .venv/site-packages)
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ==============================================================================
# Stage 2: Runtime
# ==============================================================================
FROM python:3.12-slim-bookworm

# GDAL runtime libs + PostgreSQL client + data loading tools (D-01).
# The `postgis` metapackage on Debian bookworm owns /usr/bin/shp2pgsql
# (verified via `apt-file search`). shp2pgsql is required by
# `geo-import setup-tiger` to load TIGER/Line shapefiles via
# Loader_Generate_Script (Phase 999.1). The postgis metapackage pulls in
# postgresql-15-postgis-3 (server extension) as a dependency; it's unused in
# this client image but adds ~30MB — acceptable cost for the client binary.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgdal-dev libexpat1 postgresql-client \
        postgis \
        unzip wget && \
    rm -rf /var/lib/apt/lists/*

# Non-root appuser (UID 1000, D-03)
RUN groupadd -r appuser --gid 1000 && \
    useradd -r -g appuser --uid 1000 --home /app appuser

WORKDIR /app

# Transfer venv and application artifacts from builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/scripts /app/scripts

# GIS data directory (owned by appuser for Tiger data imports, Pitfall 2)
RUN mkdir -p /gisdata/temp && chown -R appuser:appuser /gisdata

ARG GIT_COMMIT=unknown
ENV PATH="/app/.venv/bin:$PATH" \
    GIT_COMMIT=${GIT_COMMIT}

USER appuser

EXPOSE 8000

# Exec-form CMD per D-12 and DEPLOY-01 (no shell wrapper — enables clean SIGTERM)
CMD ["uvicorn", "civpulse_geo.main:app", "--host", "0.0.0.0", "--port", "8000"]
