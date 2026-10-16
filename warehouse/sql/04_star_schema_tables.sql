-- ===============================================
-- Creating Dimension Tables
-- ===============================================

CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_key        INTEGER PRIMARY KEY, -- YYYYMMDD

    full_date       DATE NOT NULL UNIQUE,
    day             SMALLINT NOT NULL,
    day_name        VARCHAR(10) NOT NULL,
    day_of_week     SMALLINT NOT NULL,
    week_of_year    SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    quarter         SMALLINT NOT NULL,
    year            SMALLINT NOT NULL,

    is_weekend      BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_time (
    time_key        INTEGER PRIMARY KEY, -- HHMMSS

    full_time       TIME NOT NULL UNIQUE,
    hour            SMALLINT NOT NULL,
    minute          SMALLINT NOT NULL,
    second          SMALLINT NOT NULL,

    am_pm           VARCHAR(2) NOT NULL,
    time_period     VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_vendor (
    vendor_key      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    vendor_id       SMALLINT NOT NULL UNIQUE,
    vendor_name     VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_location (
    location_key    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    location_id     SMALLINT NOT NULL UNIQUE,
    borough         VARCHAR(50) NOT NULL,
    locaation_zone  VARCHAR(100) NOT NULL,
    service_zone    VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_payment (
    payment_key         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    payment_type_id     SMALLINT NOT NULL UNIQUE,
    payment_description VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_ratecode (
    ratecode_key    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    ratecode_id     SMALLINT NOT NULL UNIQUE,
    ratecode_name   VARCHAR(100) NOT NULL
);


-- ===============================================
-- Creating Fact Table
-- ===============================================

CREATE TABLE IF NOT EXISTS gold.fact_yellow_taxi_trips (

    -- Primary key
    trip_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Source lineage
    bronze_trip_id BIGINT NOT NULL UNIQUE,

    -- Date dimension references
    pickup_date_key     INTEGER NOT NULL,
    dropoff_date_key    INTEGER NOT NULL,

    -- Time dimension references
    pickup_time_key     INTEGER NOT NULL,
    dropoff_time_key    INTEGER NOT NULL,

    -- Other dimension references
    vendor_key              INTEGER NOT NULL,
    pickup_location_key     INTEGER,
    dropoff_location_key    INTEGER,
    payment_key             INTEGER,
    ratecode_key            INTEGER,

    -- Trip measures
    passenger_count         SMALLINT,
    trip_distance           NUMERIC(10, 2),
    trip_duration_minutes   NUMERIC(10, 2),

    -- Fare measures
    fare_amount             NUMERIC(10, 2),
    extra                   NUMERIC(10, 2),
    mta_tax                 NUMERIC(10, 2),
    tip_amount              NUMERIC(10, 2),
    tolls_amount            NUMERIC(10, 2),
    improvement_surcharge   NUMERIC(10, 2),
    total_amount            NUMERIC(10, 2),
    congestion_surcharge    NUMERIC(10, 2),
    airport_fee             NUMERIC(10, 2),
    cbd_congestion_fee      NUMERIC(10, 2),

    -- Foreign key constraints
    CONSTRAINT fk_fact_silver_trip
        FOREIGN KEY (bronze_trip_id)
        REFERENCES silver.yellow_taxi_trips(bronze_trip_id),

    CONSTRAINT fk_fact_pickup_date
        FOREIGN KEY (pickup_date_key)
        REFERENCES gold.dim_date(date_key),

    CONSTRAINT fk_fact_dropoff_date
        FOREIGN KEY (dropoff_date_key)
        REFERENCES gold.dim_date(date_key),

    CONSTRAINT fk_fact_pickup_time
        FOREIGN KEY (pickup_time_key)
        REFERENCES gold.dim_time(time_key),

    CONSTRAINT fk_fact_dropoff_time
        FOREIGN KEY (dropoff_time_key)
        REFERENCES gold.dim_time(time_key),

    CONSTRAINT fk_fact_vendor
        FOREIGN KEY (vendor_key)
        REFERENCES gold.dim_vendor(vendor_key),

    CONSTRAINT fk_fact_pickup_location
        FOREIGN KEY (pickup_location_key)
        REFERENCES gold.dim_location(location_key),

    CONSTRAINT fk_fact_dropoff_location
        FOREIGN KEY (dropoff_location_key)
        REFERENCES gold.dim_location(location_key),

    CONSTRAINT fk_fact_payment
        FOREIGN KEY (payment_key)
        REFERENCES gold.dim_payment(payment_key),

    CONSTRAINT fk_fact_ratecode
        FOREIGN KEY (ratecode_key)
        REFERENCES gold.dim_ratecode(ratecode_key)
);