FROM mediagis/nominatim@sha256:3c49ad9443baab1f1ea13a6b1355fa377ae5fb0874dc328cba9b97a0ca7914bb

# Preserve PostgreSQL 16 and the existing Nominatim/PostGIS stack.
# Fail the build if the repository does not supply the reviewed patch release.
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        'postgresql-16=16.15-0ubuntu0.24.04.1' 'postgresql-client-16=16.15-0ubuntu0.24.04.1' 'libpq5=16.15-0ubuntu0.24.04.1' \
    && /usr/lib/postgresql/16/bin/postgres --version | grep -F ' 16.15 ' \
    && rm -rf /var/lib/apt/lists/*
