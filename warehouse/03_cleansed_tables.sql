-- ==============================================
-- Creation of Tables for Silver Layer
-- ==============================================

CREATE TABLE IF NOT EXISTS silver.yellow_taxi_trips (
    -- Data lineage
    bronze_trip_id BIGINT PRIMARY KEY
        REFERENCES bronze.yellow_taxi_trips(trip_id),

    -- Trip Identifiers
    vendor_id               SMALLINT NOT NULL,
    pickup_datetime         TIMESTAMP NOT NULL,
    dropoff_datetime        TIMESTAMP NOT NULL,

    -- Trip Information
    passenger_count         SMALLINT,
    trip_distance           NUMERIC(10, 2),

    -- Classification
    ratecode_id             SMALLINT,
    store_and_fwd_flag      CHAR(1),
    pickup_location_id      INTEGER,
    dropoff_location_id     INTEGER,
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

    -- Derived information
    trip_duration_minutes NUMERIC(10, 2),

    -- Data quality and processing metadata
    silver_loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_trip_datetime
        CHECK (dropoff_datetime >= pickup_datetime),

    CONSTRAINT chk_trip_distance
        CHECK (trip_distance IS NULL OR trip_distance >= 0),

    CONSTRAINT chk_passenger_count
        CHECK (passenger_count IS NULL OR passenger_count >= 0),

    CONSTRAINT chk_store_and_fwd_flag
        CHECK (
            store_and_fwd_flag IS NULL
            OR store_and_fwd_flag IN ('Y', 'N')
        ),

    CONSTRAINT chk_trip_duration
        CHECK (
            trip_duration_minutes IS NULL
            OR trip_duration_minutes >= 0
        ),

    -- Reference relationships
    CONSTRAINT fk_silver_vendor
        FOREIGN KEY (vendor_id)
        REFERENCES silver.ref_vendor(vendor_id),

    CONSTRAINT fk_silver_ratecode
        FOREIGN KEY (ratecode_id)
        REFERENCES silver.ref_ratecode(ratecode_id),

    CONSTRAINT fk_silver_payment
        FOREIGN KEY (payment_type_id)
        REFERENCES silver.ref_payment_type(payment_type_id),

    CONSTRAINT fk_silver_pickup_location
        FOREIGN KEY (pickup_location_id)
        REFERENCES silver.ref_location(location_id),

    CONSTRAINT fk_silver_dropoff_location
        FOREIGN KEY (dropoff_location_id)
        REFERENCES silver.ref_location(location_id)

);

CREATE TABLE IF NOT EXISTS silver.ref_location (
    location_id     SMALLINT PRIMARY KEY,
    Borough         VARCHAR(50) NOT NULL,
    location_zone   VARCHAR(100) NOT NULL,
    service_zone    VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.ref_providers (
    vendor_id       SMALLINT PRIMARY KEY,
    provider_name   VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.ref_ratecode (
    ratecode_id    SMALLINT PRIMARY KEY,
    ratecode_name  VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.ref_payment_type (
    type_id         SMALLINT PRIMARY KEY,
    payment_type    VARCHAR(100) NOT NULL
);