/*
==================================================
Create Database and Schemas
==================================================

Script Purpose:
    This script creates a new database named
    DataWarehouse if it does not exist.

    It also creates the schemas needed for a
    three-tier Medallion Data Architecture:

    1. Bronze - Raw data layer
    2. Silver - Data cleaning and transformation
    3. Gold   - BI and analytics layer

WARNING:
    Running this script will DROP the existing
    DataWarehouse database if it exists.
    All existing data will be permanently deleted.
==================================================
*/

-- ==================================================
-- 1. DROP AND RECREATE DATABASE
-- ==================================================

-- Disconnect existing connections before dropping
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'DataWarehouse'
  AND pid <> pg_backend_pid();

-- Drop existing database
DROP DATABASE IF EXISTS "DataWarehouse";

-- Create new database
CREATE DATABASE "DataWarehouse";


-- ==================================================
-- 2. CREATE DATA LAYER SCHEMAS
-- ==================================================

-- IMPORTANT:
-- Connect to DataWarehouse before executing this section.
-- In psql, use: \c "DataWarehouse"

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE SCHEMA IF NOT EXISTS silver;

CREATE SCHEMA IF NOT EXISTS gold;


-- ==================================================
-- 3. VERIFY CREATED SCHEMAS
-- ==================================================

SELECT schema_name
FROM information_schema.schemata
WHERE schema_name IN ('bronze', 'silver', 'gold')
ORDER BY schema_name;