-- scripts/provision-db.sql
-- Idempotent provisioning for civpulse geo-api databases
-- Run as: psql -h thor.tailb56d83.ts.net -U postgres -f scripts/provision-db.sql
--
-- WARNING: This is a shared production PostgreSQL server.
-- All statements use IF NOT EXISTS guards. No destructive operations.
--
-- IMPORTANT: Replace CHANGE_ME_DEV and CHANGE_ME_PROD with real passwords
-- before executing. Store the passwords in K8s Secrets (Phase 20, DEPLOY-05).
--
--   geo_dev  password → civpulse-dev namespace Secret (key: db-password)
--   geo_prod password → civpulse-prod namespace Secret (key: db-password)

-- ============================================================
-- Dev environment
-- ============================================================

-- Create dev role (IF NOT EXISTS via DO block -- safe for roles)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'geo_dev') THEN
    CREATE ROLE geo_dev WITH LOGIN PASSWORD 'CHANGE_ME_DEV';
  END IF;
END $$;

-- Create dev database (conditional via \gexec -- safe for CREATE DATABASE outside transaction)
SELECT 'CREATE DATABASE civpulse_geo_dev OWNER geo_dev ENCODING ''UTF8'' LC_COLLATE ''en_US.UTF-8'' LC_CTYPE ''en_US.UTF-8'' TEMPLATE template0;'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'civpulse_geo_dev')
\gexec

-- Connect to dev database and create extensions (as postgres superuser, Pitfall 6)
\connect civpulse_geo_dev
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
GRANT ALL PRIVILEGES ON DATABASE civpulse_geo_dev TO geo_dev;
GRANT ALL ON SCHEMA public TO geo_dev;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO geo_dev;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO geo_dev;

-- ============================================================
-- Prod environment
-- ============================================================

-- Reconnect to default database for role/database creation
\connect postgres

-- Create prod role
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'geo_prod') THEN
    CREATE ROLE geo_prod WITH LOGIN PASSWORD 'CHANGE_ME_PROD';
  END IF;
END $$;

-- Create prod database
SELECT 'CREATE DATABASE civpulse_geo_prod OWNER geo_prod ENCODING ''UTF8'' LC_COLLATE ''en_US.UTF-8'' LC_CTYPE ''en_US.UTF-8'' TEMPLATE template0;'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'civpulse_geo_prod')
\gexec

-- Connect to prod database and create extensions
\connect civpulse_geo_prod
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
GRANT ALL PRIVILEGES ON DATABASE civpulse_geo_prod TO geo_prod;
GRANT ALL ON SCHEMA public TO geo_prod;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO geo_prod;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO geo_prod;
