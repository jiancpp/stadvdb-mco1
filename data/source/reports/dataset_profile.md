# NYC TLC Yellow Taxi Trip Records (2025) - Dataset Profile

**Generated:** 2026-10-16 23:14:02  
**Target Source Database:** `nyc_taxi_source`  
**Source Table:** `yellow_tripdata_2025`  

## 1. Executive Summary

- **Total Monthly Files:** 12 (January through December 2025)
- **Total Parquet Size:** 791.52 MB (829,973,299 bytes)
- **Total Parquet Rows:** 48,722,602
- **Total PostgreSQL Rows:** 48,722,602
- **Ingestion Status:** EXACT MATCH (100% Fidelity)

## 2. Monthly Source Files Breakdown

| Month / Filename | File Size (MB) | Parquet Rows | DB Rows | Match Status |
| :--- | :---: | :---: | :---: | :---: |
| `yellow_tripdata_2025-01.parquet` | 56.42 | 3,475,226 | 3,475,226 | ✅ MATCH |
| `yellow_tripdata_2025-02.parquet` | 57.55 | 3,577,543 | 3,577,543 | ✅ MATCH |
| `yellow_tripdata_2025-03.parquet` | 66.72 | 4,145,257 | 4,145,257 | ✅ MATCH |
| `yellow_tripdata_2025-04.parquet` | 64.23 | 3,970,553 | 3,970,553 | ✅ MATCH |
| `yellow_tripdata_2025-05.parquet` | 74.23 | 4,591,845 | 4,591,845 | ✅ MATCH |
| `yellow_tripdata_2025-06.parquet` | 70.14 | 4,322,960 | 4,322,960 | ✅ MATCH |
| `yellow_tripdata_2025-07.parquet` | 63.84 | 3,898,963 | 3,898,963 | ✅ MATCH |
| `yellow_tripdata_2025-08.parquet` | 59.41 | 3,574,091 | 3,574,091 | ✅ MATCH |
| `yellow_tripdata_2025-09.parquet` | 69.08 | 4,251,015 | 4,251,015 | ✅ MATCH |
| `yellow_tripdata_2025-10.parquet` | 71.78 | 4,428,699 | 4,428,699 | ✅ MATCH |
| `yellow_tripdata_2025-11.parquet` | 67.84 | 4,181,444 | 4,181,444 | ✅ MATCH |
| `yellow_tripdata_2025-12.parquet` | 70.29 | 4,305,006 | 4,305,006 | ✅ MATCH |
| **TOTAL** | **791.52** | **48,722,602** | **48722602** | |

## 3. Schema & Column Specifications

All 12 monthly Parquet files possess **identical 20-column schemas**. Schema details and PostgreSQL mappings:

| Column Name | Parquet Arrow Type | PostgreSQL Type | Nullable | Null Count | Null % |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `VendorID` | `int32` | `INTEGER` | YES | 0 | 0.00% |
| `tpep_pickup_datetime` | `timestamp[us]` | `TIMESTAMP` | YES | 0 | 0.00% |
| `tpep_dropoff_datetime` | `timestamp[us]` | `TIMESTAMP` | YES | 0 | 0.00% |
| `passenger_count` | `int64` | `BIGINT` | YES | 11,611,894 | 23.83% |
| `trip_distance` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `RatecodeID` | `int64` | `BIGINT` | YES | 11,611,894 | 23.83% |
| `store_and_fwd_flag` | `large_string` | `VARCHAR(10)` | YES | 11,611,894 | 23.83% |
| `PULocationID` | `int32` | `INTEGER` | YES | 0 | 0.00% |
| `DOLocationID` | `int32` | `INTEGER` | YES | 0 | 0.00% |
| `payment_type` | `int64` | `BIGINT` | YES | 0 | 0.00% |
| `fare_amount` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `extra` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `mta_tax` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `tip_amount` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `tolls_amount` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `improvement_surcharge` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `total_amount` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |
| `congestion_surcharge` | `double` | `DOUBLE PRECISION` | YES | 11,611,894 | 23.83% |
| `Airport_fee` | `double` | `DOUBLE PRECISION` | YES | 11,611,894 | 23.83% |
| `cbd_congestion_fee` | `double` | `DOUBLE PRECISION` | YES | 0 | 0.00% |

## 4. Key Metric Distributions & Anomalies

### Trip Distances
- **Minimum Distance:** 0.0 miles
- **Maximum Distance:** 397,994.37 miles
- **Mean (Average) Distance:** 6.84 miles
- **Median Distance:** 1.85 miles
- **Zero-Distance Trips (distance = 0):** 1,402,958 (2.88%)
- **Negative Distance Records:** 0
- **Extreme Distance Trips (> 100 miles):** 2,870

### Fares and Total Amounts
- **Minimum Fare Amount:** $-1807.60
- **Maximum Fare Amount:** $863,372.12
- **Average Fare Amount:** $18.42
- **Median Fare Amount:** $13.58
- **Negative Fare Amounts:** 2,848,620 (cancellations/refunds/disputes)
- **Zero Fare Amounts:** 21,614
- **Extreme Fares (> $500):** 844
- **Minimum Total Amount:** $-1832.85
- **Maximum Total Amount:** $863,380.37
- **Negative Total Amounts:** 973,721

### Temporal Coverage & Anomalies
- **Earliest Pickup:** `2007-12-05 18:45:00`
- **Latest Pickup:** `2025-12-31 23:59:59`
- **Earliest Dropoff:** `2007-12-05 19:02:00`
- **Latest Dropoff:** `2026-01-05 13:00:34`
- **Pickups Outside 2025 Calendar Year:** 29 (meter clock misconfigurations / outlier records preserved)
- **Dropoff Recorded Before Pickup:** 2,235

### Passenger Count & Trip Duplicates
- **Min / Max / Avg Passengers:** 0 / 9 / 1.30
- **Zero Passenger Trips:** 260,062
- **High Passenger Trips (> 6):** 146
- **Null Passenger Counts:** 11,611,894
- **Duplicate-Looking Trip Groups:** 4,828 (trips sharing identical vendor, timestamps, locations, and fare; faithfully preserved as natural occurrences)

## 5. Dataset Observations & Quality Summary

1. **Complete Schema Uniformity:** Across all 12 monthly Parquet files, all 20 columns and data types are perfectly identical.
2. **Faithful Ingestion:** As required by academic and data warehousing principles, no negative fares, 0-passenger rides, or dates outside 2025 were removed or modified during ingestion. All original source anomalies remain intact for upstream transformation in the dimensional warehouse.
3. **Lineage Tracking:** Every record is tagged with its `source_file` and import timestamp to guarantee full traceability.
