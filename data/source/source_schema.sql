-- ============================================================================
-- STADVDB MCO1 - Source Database Schema
-- Database: nyc_taxi_source
-- Dataset: NYC TLC Yellow Taxi Trip Records (January - December 2025)
-- ============================================================================

-- Table: import_manifest
-- Tracks import execution, file metadata, row count audit, and status.
CREATE TABLE IF NOT EXISTS import_manifest (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    file_size_bytes BIGINT NOT NULL,
    parquet_row_count BIGINT NOT NULL,
    imported_row_count BIGINT DEFAULT 0,
    import_status VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED'
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_time_seconds NUMERIC(10, 2),
    checksum_md5 VARCHAR(64),
    error_message TEXT
);

-- Table: yellow_tripdata_2025
-- Faithfully stores the raw trip records from all 12 monthly 2025 Parquet files.
-- All source columns are explicitly nullable without domain constraints to
-- ensure full fidelity with original data (including negatives, outliers, and nulls).
CREATE TABLE IF NOT EXISTS yellow_tripdata_2025 (
    trip_id BIGSERIAL PRIMARY KEY,
    
    -- 20 Original Parquet Columns (unquoted for case-insensitive querying in PostgreSQL)
    vendorid INTEGER,
    tpep_pickup_datetime TIMESTAMP,
    tpep_dropoff_datetime TIMESTAMP,
    passenger_count BIGINT,
    trip_distance DOUBLE PRECISION,
    ratecodeid BIGINT,
    store_and_fwd_flag VARCHAR(10),
    pulocationid INTEGER,
    dolocationid INTEGER,
    payment_type BIGINT,
    fare_amount DOUBLE PRECISION,
    extra DOUBLE PRECISION,
    mta_tax DOUBLE PRECISION,
    tip_amount DOUBLE PRECISION,
    tolls_amount DOUBLE PRECISION,
    improvement_surcharge DOUBLE PRECISION,
    total_amount DOUBLE PRECISION,
    congestion_surcharge DOUBLE PRECISION,
    airport_fee DOUBLE PRECISION,
    cbd_congestion_fee DOUBLE PRECISION,
    
    -- Source File Lineage Metadata
    source_file VARCHAR(100) NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance, validation, and ETL extraction
CREATE INDEX IF NOT EXISTS idx_yellow_tripdata_source_file 
    ON yellow_tripdata_2025 (source_file);

CREATE INDEX IF NOT EXISTS idx_yellow_tripdata_pickup 
    ON yellow_tripdata_2025 (tpep_pickup_datetime);
