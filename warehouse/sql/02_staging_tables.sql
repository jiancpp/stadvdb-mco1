/*
==================================================
Create Staging Tables
==================================================

Script Purpose:
    This script creates tables used to temporarily
    hold and cleanse raw data.

    The created tables loosely matches the raw
    data sources
    
==================================================
*/


-- ==============================================
-- 1. Creation of Tables for Bronze Layer
-- ==============================================

CREATE TABLE IF NOT EXISTS bronze.yellow_taxi_trips (
    -- Original source identifier
    source_trip_id          BIGINT PRIMARY KEY,

    -- Original source columns
    vendorid                INTEGER,
    tpep_pickup_datetime    TIMESTAMP,
    tpep_dropoff_datetime   TIMESTAMP,
    passenger_count         BIGINT,
    trip_distance           DOUBLE PRECISION,
    ratecodeid              BIGINT,
    store_and_fwd_flag      VARCHAR(10),
    pulocationid            INTEGER,
    dolocationid            INTEGER,
    payment_type            BIGINT,

    -- Fare information
    fare_amount             DOUBLE PRECISION,
    extra                   DOUBLE PRECISION,
    mta_tax                 DOUBLE PRECISION,
    tip_amount              DOUBLE PRECISION,
    tolls_amount            DOUBLE PRECISION,
    improvement_surcharge   DOUBLE PRECISION,
    total_amount            DOUBLE PRECISION,
    congestion_surcharge    DOUBLE PRECISION,
    airport_fee             DOUBLE PRECISION,
    cbd_congestion_fee      DOUBLE PRECISION,

    -- Source lineage
    source_file             VARCHAR(100) NOT NULL,
    imported_at             TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS bronze.ref_location (
    location_id INTEGER PRIMARY KEY,
    borough VARCHAR(50),
    zone VARCHAR(100),
    service_zone VARCHAR(50)
);