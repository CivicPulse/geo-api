# Nominatim PostgreSQL patch

Retains the deployed Nominatim 5.2 base digest and PostGIS 3.4.2, replacing only PostgreSQL 16 packages with Ubuntu security version 16.15. Deployment must use the tested image digest.

The legacy deployment mounts storage at the PG14 path while PG16 writes into its container layer. Before replacing that pod, take an encrypted off-host logical backup, seed the unused PVC with a consistent pg_basebackup, verify its manifest, and test PostgreSQL and geocoding against a separate copy. Use the seeded `pg16` subdirectory mounted at `/var/lib/postgresql/16/main`. Preserve the `import-finished` marker to avoid reimporting the PBF. Verify replication remains disabled and no application writes occur between seed and cutover.

Release notes reviewed: https://www.postgresql.org/docs/16/release-16-15.html and intervening 16.12–16.14 releases. Check installed extensions and logical slots for the documented follow-up actions.

Rollback must retain the corrected persistent mount and seeded data. Never revert to the old PG14 mount: the old database lived in a deleted container. The old pinned Nominatim image can use the persistent PG16 directory if a binary rollback is needed. Preserve backups independently of this repository.
