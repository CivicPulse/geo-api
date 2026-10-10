FROM overv/openstreetmap-tile-server@sha256:671bf8cf97cf65e21f40d2d53b4ae0062a9afcefffd1c7ce8f9b763f2a5d274f

# Preserve PostgreSQL 14 and the existing PostGIS/style stack.
# Fail the build if the repository does not supply the reviewed patch release.
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        'postgresql-14=14.24-0ubuntu0.22.04.1' 'postgresql-client-14=14.24-0ubuntu0.22.04.1' 'libpq5=14.24-0ubuntu0.22.04.1' \
    && /usr/lib/postgresql/14/bin/postgres --version | grep -F ' 14.24 ' \
    && rm -rf /var/lib/apt/lists/*
