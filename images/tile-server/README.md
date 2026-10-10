# Tile server PostgreSQL maintenance image

Retains the deployed OpenStreetMap tile server 2.3.0 image by digest, PostgreSQL major 14, PostGIS and rendering assets. Installs the exact Ubuntu PostgreSQL 14.24 server, client and libpq packages. The build fails if those packages or the expected binary version are unavailable.

The GIS image workflow publishes a commit-tagged GHCR image. Deployment must pin its digest only after an isolated database restore and rendered-tile check. Do not mount the production database into the test container.

For a production cluster originally on PostgreSQL 14.7, upgrading the binary alone is insufficient:

- Apply the packaged `fix-CVE-2024-4317.sql` to every database, including templates, as described in the PostgreSQL 14.12 release notes.
- Rebuild existing GiST indexes after upgrading, as recommended by PostgreSQL 14.10. Check other index types against intervening release notes.
- Keep verified off-host database/role backups and the previous image digest. PostgreSQL 14 requires a separate major-version migration before its November 2026 end of support.

References: [14.10](https://www.postgresql.org/docs/release/14.10/), [14.12](https://www.postgresql.org/docs/release/14.12/), [14.24](https://www.postgresql.org/docs/release/14.24/).
