# STADVDB MCO1 - Source Database ETL Handoff & Integration Guide

**Document Purpose:** This document provides the ETL and Data Warehouse engineering team members with complete specifications for integrating the PostgreSQL source database (`nyc_taxi_source`) into the warehouse ETL pipeline.

---

## 1. Database & Table Identification

| Property | Value |
| :--- | :--- |
| **Database Management System** | PostgreSQL 18.x / 17.x / 16.x |
| **Source Database Name** | `nyc_taxi_source` |
| **Primary Source Table** | `yellow_tripdata_2025` |
| **Audit Manifest Table** | `import_manifest` |
| **Coverage Period** | January 1, 2025 – December 31, 2025 (12 monthly files) |
| **Total Source Records** | **48,722,602 rows** |

---

## 2. Table Schemas & Column Specifications

### Primary Table: `yellow_tripdata_2025`

| Column Name | PostgreSQL Data Type | Nullable | Description & Notes |
| :--- | :--- | :---: | :--- |
| `trip_id` | `BIGSERIAL PRIMARY KEY` | NO | Auto-incrementing surrogate ID for row identification |
| `vendorid` | `INTEGER` | YES | Code indicating the TPEP provider (1=Creative Mobile, 2=VeriFone Inc, etc.) |
| `tpep_pickup_datetime` | `TIMESTAMP` | YES | The date and time when the meter was engaged |
| `tpep_dropoff_datetime` | `TIMESTAMP` | YES | The date and time when the meter was disengaged |
| `passenger_count` | `BIGINT` | YES | Number of passengers in the vehicle (contains NULLs and 0s) |
| `trip_distance` | `DOUBLE PRECISION` | YES | Elapsed trip distance in miles |
| `ratecodeid` | `BIGINT` | YES | Final rate code in effect (1=Standard, 2=JFK, 3=Newark, 4=Nassau/Westchester, 5=Negotiated, 6=Group) |
| `store_and_fwd_flag` | `VARCHAR(10)` | YES | 'Y' = store and forward trip, 'N' = not a store and forward trip |
| `pulocationid` | `INTEGER` | YES | TLC Taxi Zone in which the taximeter was engaged |
| `dolocationid` | `INTEGER` | YES | TLC Taxi Zone in which the taximeter was disengaged |
| `payment_type` | `BIGINT` | YES | Numeric code signifying how the passenger paid (1=Credit card, 2=Cash, 3=No charge, 4=Dispute, etc.) |
| `fare_amount` | `DOUBLE PRECISION` | YES | The time-and-distance fare calculated by the meter |
| `extra` | `DOUBLE PRECISION` | YES | Miscellaneous extras and surcharges ($0.50 and $1.00 rush hour / overnight charges) |
| `mta_tax` | `DOUBLE PRECISION` | YES | $0.50 MTA tax automatically triggered based on the metered rate |
| `tip_amount` | `DOUBLE PRECISION` | YES | Tip amount (automatically populated for credit card trips; cash tips not included) |
| `tolls_amount` | `DOUBLE PRECISION` | YES | Total amount of all tolls paid in trip |
| `improvement_surcharge` | `DOUBLE PRECISION` | YES | $0.30 / $1.00 improvement surcharge assessed on hailed trips |
| `total_amount` | `DOUBLE PRECISION` | YES | The total amount charged to passengers (does not include cash tips) |
| `congestion_surcharge` | `DOUBLE PRECISION` | YES | Congestion surcharge for trips in Manhattan congestion zone |
| `airport_fee` | `DOUBLE PRECISION` | YES | $1.25 / $1.75 fee for pick up at LaGuardia and JFK Airports |
| `cbd_congestion_fee` | `DOUBLE PRECISION` | YES | Central Business District tolling surcharge |
| `source_file` | `VARCHAR(100)` | NO | Original Parquet filename (e.g., `yellow_tripdata_2025-01.parquet`) |
| `imported_at` | `TIMESTAMP WITH TIME ZONE` | NO | Ingestion timestamp |

### Audit Table: `import_manifest`

Tracks status, execution runtime, and row-count verification per monthly file.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `SERIAL PRIMARY KEY` | Audit entry ID |
| `filename` | `VARCHAR(255) UNIQUE` | Parquet filename |
| `file_size_bytes` | `BIGINT` | Source file size on disk |
| `parquet_row_count` | `BIGINT` | Number of rows in source Parquet file |
| `imported_row_count` | `BIGINT` | Number of rows successfully written to PostgreSQL |
| `import_status` | `VARCHAR(50)` | Status: `COMPLETED`, `IN_PROGRESS`, `FAILED` |
| `started_at` | `TIMESTAMP WITH TIME ZONE` | Import start timestamp |
| `completed_at` | `TIMESTAMP WITH TIME ZONE` | Import completion timestamp |
| `execution_time_seconds` | `NUMERIC(10,2)` | Ingestion runtime |
| `error_message` | `TEXT` | Logged error message if failure occurred |

### Reference Table: `taxi_zone_lookup` (265 zones)

Used to populate the **`Dim_Location` / `Dim_Zone`** dimension table in the warehouse.

| Column | Type | Description |
| :--- | :--- | :--- |
| `locationid` | `INTEGER PRIMARY KEY` | Zone ID (1 to 265) matching `pulocationid` and `dolocationid` |
| `borough` | `VARCHAR(50)` | NYC Borough (e.g., `Manhattan`, `Queens`, `Brooklyn`, `Bronx`, `Staten Island`, `EWR`) |
| `zone` | `VARCHAR(100)` | Neighborhood / Zone name (e.g., `JFK Airport`, `Times Sq/Theatre District`) |
| `service_zone` | `VARCHAR(50)` | Service classification (`Yellow Zone`, `Boro Zone`, `Airports`, `EWR`) |

#### Example SQL Join for ETL extraction:
```sql
SELECT 
    t.trip_id,
    t.tpep_pickup_datetime,
    t.fare_amount,
    pz.borough AS pickup_borough,
    pz.zone AS pickup_zone,
    dz.borough AS dropoff_borough,
    dz.zone AS dropoff_zone
FROM yellow_tripdata_2025 t
LEFT JOIN taxi_zone_lookup pz ON t.pulocationid = pz.locationid
LEFT JOIN taxi_zone_lookup dz ON t.dolocationid = dz.locationid
LIMIT 5;
```

---

## 3. Connection Configuration

Group members developing ETL scripts in Python should configure connection parameters through environment variables or `.env`:

```ini
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=<your_local_password>
SOURCE_DB=nyc_taxi_source
```

### Python Connection Example (psycopg 3):
```python
import psycopg

conn = psycopg.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="<your_password>",
    dbname="nyc_taxi_source"
)
```

---

## 4. Documented Source Data Quality Issues & Transformations Needed

During profiling of the raw 2025 dataset, the following data quality issues were identified. As per source database guidelines, **all raw data was preserved 100% faithfully**. The ETL team should address these during extraction and dimensional transformation:

1. **Negative Fares & Negative Total Amounts:**
   - Negative values exist in `fare_amount` and `total_amount` representing ride cancellations, disputed transactions, or meter voids.
   - *ETL Action:* Flag or handle as transaction reversals in the fact table.

2. **Zero-Distance Trips:**
   - Over 500,000 records have `trip_distance = 0.0` but non-zero fares (e.g. minimum fares, base charges, or immediate dropoffs).
   - *ETL Action:* Treat as valid transactions unless filtering by trip distance for velocity analysis.

3. **Timestamps Outside 2025:**
   - A small number of records contain pickup dates in prior years (e.g., 2008, 2024) or future years due to taximeter clock misconfigurations.
   - *ETL Action:* Filter out or route to an exception table during date dimension lookups.

4. **Null Values in Optional Surcharges:**
   - Fields such as `passenger_count`, `congestion_surcharge`, `airport_fee`, and `cbd_congestion_fee` contain NULL values.
   - *ETL Action:* Default to `0.0` for numeric surcharges and `Unknown` (-1) for foreign key dimensions.

5. **Duplicate-Looking Trips:**
   - Multiple trips share identical pickup timestamps, dropoff timestamps, and vendor IDs. In taxi operations, two separate vehicles from the same vendor can hail at the exact same second.
   - *ETL Action:* Use the source `trip_id` as the operational key rather than natural composite keys.

---

## 5. Source-to-Warehouse Reconciliation Queries

The following queries should be executed after running the warehouse ETL pipeline to verify data integrity:

```sql
-- 1. Total row count reconciliation
SELECT 
    (SELECT COUNT(*) FROM yellow_tripdata_2025) AS source_total_rows,
    (SELECT COUNT(*) FROM fact_taxi_trips) AS warehouse_fact_rows;

-- 2. Monthly count reconciliation
SELECT 
    s.source_file,
    COUNT(s.trip_id) AS source_count,
    COUNT(w.trip_id) AS warehouse_count
FROM yellow_tripdata_2025 s
LEFT JOIN fact_taxi_trips w ON s.trip_id = w.source_trip_id
GROUP BY s.source_file
ORDER BY s.source_file;
```

---

## 6. Current Dimensional Warehouse Status

- **Status:** **PENDING**
- The repository's `warehouse/` and `etl/` directories currently contain placeholder files (`01_create_schemas.sql` and `pipeline.py`).
- Once the warehouse schemas and ETL scripts are drafted by groupmates, end-to-end reconciliation testing can proceed.
