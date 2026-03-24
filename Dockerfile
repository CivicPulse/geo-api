FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# System libs required by fiona/GDAL and Tiger loader (shp2pgsql, wget, psql, unzip)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libexpat1 libgdal-dev postgis postgresql-client unzip wget && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /gisdata/temp

# Install dependencies first (cached layer — only rebuilds when lock file changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy source and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
ENV PATH="/app/.venv/bin:$PATH"

CMD ["bash", "scripts/docker-entrypoint.sh"]
