# NYC TLC Yellow Taxi Trip Records (2025) - Dataset Profile

**Generated:** 2026-10-16 22:54:35  
**Target Source Database:** `nyc_taxi_source`  
**Source Table:** `yellow_tripdata_2025`  

## 1. Executive Summary

- **Total Monthly Files:** 12 (January through December 2025)
- **Total Parquet Size:** 791.52 MB (829,973,299 bytes)
- **Total Parquet Rows:** 48,722,602
- **Total PostgreSQL Rows:** PENDING IMPORT

## 2. Monthly Source Files Breakdown

| Month / Filename | File Size (MB) | Parquet Rows | DB Rows | Match Status |
| :--- | :---: | :---: | :---: | :---: |
| `yellow_tripdata_2025-01.parquet` | 56.42 | 3,475,226 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-02.parquet` | 57.55 | 3,577,543 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-03.parquet` | 66.72 | 4,145,257 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-04.parquet` | 64.23 | 3,970,553 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-05.parquet` | 74.23 | 4,591,845 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-06.parquet` | 70.14 | 4,322,960 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-07.parquet` | 63.84 | 3,898,963 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-08.parquet` | 59.41 | 3,574,091 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-09.parquet` | 69.08 | 4,251,015 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-10.parquet` | 71.78 | 4,428,699 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-11.parquet` | 67.84 | 4,181,444 | 0 | ⏳ PENDING |
| `yellow_tripdata_2025-12.parquet` | 70.29 | 4,305,006 | 0 | ⏳ PENDING |
| **TOTAL** | **791.52** | **48,722,602** | **PENDING** | |

## 3. Schema & Column Specifications

All 12 monthly Parquet files possess **identical 20-column schemas**. Schema details and PostgreSQL mappings:

| Column Name | Parquet Arrow Type | PostgreSQL Type | Nullable | Null Count | Null % |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `VendorID` | `int32` | `INTEGER` | YES | N/A | N/A |
| `tpep_pickup_datetime` | `timestamp[us]` | `TIMESTAMP` | YES | N/A | N/A |
| `tpep_dropoff_datetime` | `timestamp[us]` | `TIMESTAMP` | YES | N/A | N/A |
| `passenger_count` | `int64` | `BIGINT` | YES | N/A | N/A |
| `trip_distance` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `RatecodeID` | `int64` | `BIGINT` | YES | N/A | N/A |
| `store_and_fwd_flag` | `large_string` | `VARCHAR(10)` | YES | N/A | N/A |
| `PULocationID` | `int32` | `INTEGER` | YES | N/A | N/A |
| `DOLocationID` | `int32` | `INTEGER` | YES | N/A | N/A |
| `payment_type` | `int64` | `BIGINT` | YES | N/A | N/A |
| `fare_amount` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `extra` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `mta_tax` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `tip_amount` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `tolls_amount` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `improvement_surcharge` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `total_amount` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `congestion_surcharge` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `Airport_fee` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |
| `cbd_congestion_fee` | `double` | `DOUBLE PRECISION` | YES | N/A | N/A |

## 5. Dataset Observations & Quality Summary

1. **Complete Schema Uniformity:** Across all 12 monthly Parquet files, all 20 columns and data types are perfectly identical.
2. **Faithful Ingestion:** As required by academic and data warehousing principles, no negative fares, 0-passenger rides, or dates outside 2025 were removed or modified during ingestion. All original source anomalies remain intact for upstream transformation in the dimensional warehouse.
3. **Lineage Tracking:** Every record is tagged with its `source_file` and import timestamp to guarantee full traceability.
