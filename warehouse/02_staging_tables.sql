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
    trip_id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    "VendorID"              SMALLINT,
    tpep_pickup_datetime    TIMESTAMP,
    tpep_dropoff_datetime   TIMESTAMP,
    passenger_count         SMALLINT,
    trip_distance           NUMERIC(10, 2),
    "RatecodeID"            SMALLINT,
    store_and_fwd_flag      CHAR(1),
    "PULocationID"          INTEGER,
    "DOLocationID"          INTEGER,
    payment_type            SMALLINT,

    -- Fare breakdown
    fare_amount             NUMERIC(10, 2),
    extra                   NUMERIC(10, 2),
    mta_tax                 NUMERIC(10, 2),
    tip_amount              NUMERIC(10, 2),
    tolls_amount            NUMERIC(10, 2),
    improvement_surcharge   NUMERIC(10, 2),
    total_amount            NUMERIC(10, 2),
    congestion_surcharge    NUMERIC(10, 2),
    Airport_fee             NUMERIC(10, 2),
    cbd_congestion_fee      NUMERIC(10, 2),

    -- ETL metadata
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.ref_location (
    "LocationID"    SMALLINT PRIMARY KEY,

    "Borough"       VARCHAR(50) NOT NULL,
    "Zone"          VARCHAR(100) NOT NULL,
    service_zone    VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.ref_providers (
    "VendorID"      SMALLINT PRIMARY KEY,
    provider_name   VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.ref_ratecode (
    provider_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    "RatecodeID"    SMALLINT UNIQUE NOT NULL,
    ratecode        VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.ref_payment_type (
    type_id         SMALLINT PRIMARY KEY,
    payment_type    VARCHAR(100) NOT NULL
);

-- ============================================
-- 2. Plugging data for reference tables
-- ============================================

/* Note: Location zones are to be ingested from CSV */

INSERT INTO bronze.ref_providers ("VendorID", provider_name)
VALUES
    (1, 'Creative Mobile Technologies, LLC'),
    (2, 'Curb Mobility, LLC'),
    (6, 'Myle Technologies Inc'),
    (7, 'Helix')
ON CONFLICT ('VendorID')
DO UPDATE SET
    provider_name = EXCLUDED.provider_name;


INSERT INTO bronze.ref_ratecode ("RatecodeID", ratecode)
VALUES
    (1, 'Standard rate'),
    (2, 'JFK'),
    (3, 'Newark'),
    (4, 'Nassau or Westchester'),
    (5, 'Negotiated fare'),
    (6, 'Group ride'),
    (99, 'Null/unknown')
ON CONFLICT ('RatecodeID')
DO UPDATE SET
    ratecode = EXCLUDED.ratecode;

INSERT INTO bronze.ref_payment_type (type_id, payment_type)
VALUES
    (0, 'Flex Fare Trip'),
    (1, 'Credit Card'),
    (2, 'Cash'),
    (3, 'No charge'),
    (4, 'Dispute'),
    (5, 'Unknown'),
    (6, 'Voided trip'),
ON CONFLICT (type_id)
DO UPDATE SET
    payment_type = EXCLUDED.payment_type;
