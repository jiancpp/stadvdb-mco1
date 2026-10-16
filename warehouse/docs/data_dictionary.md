
# NYC Taxi Data Warehouse — Data Dictionary

## 1. Project Overview

**Project:** NYC Yellow Taxi Trip Data Warehouse  
**Dataset:** NYC Yellow Taxi Trip Records (January–December 2025)  
**Source Database:** `nyc_taxi_source`  
**Target Database:** `DataWarehouse`

The Data Warehouse follows a three-layer architecture:

| Layer | Purpose |
|---|---|
| Bronze | Stores raw copies of source data |
| Silver | Stores cleaned, standardized, and enriched data |
| Gold | Stores dimensional data optimized for OLAP analysis |

### Naming Conventions

- Use lowercase `snake_case` for table and column names.
- Use primary keys to uniquely identify records.
- Use foreign keys to enforce relationships.
- Preserve `source_trip_id` across layers for data lineage.
- Use surrogate keys in Gold dimensions.

---

## 2. Source Database

Database: `nyc_taxi_source`

### 2.1 yellow_tripdata_2025

**Grain:** One record per taxi trip.

| Column | Data Type | Description |
|---|---|---|
| trip_id | BIGSERIAL | Unique source trip identifier |
| vendorid | INTEGER | Taxi technology provider ID |
| tpep_pickup_datetime | TIMESTAMP | Pickup timestamp |
| tpep_dropoff_datetime | TIMESTAMP | Dropoff timestamp |
| passenger_count | BIGINT | Number of passengers |
| trip_distance | DOUBLE PRECISION | Trip distance |
| ratecodeid | BIGINT | Rate code identifier |
| store_and_fwd_flag | VARCHAR(10) | Store-and-forward flag |
| pulocationid | INTEGER | Pickup location ID |
| dolocationid | INTEGER | Dropoff location ID |
| payment_type | BIGINT | Payment type identifier |
| fare_amount | DOUBLE PRECISION | Base fare |
| extra | DOUBLE PRECISION | Additional charges |
| mta_tax | DOUBLE PRECISION | MTA tax |
| tip_amount | DOUBLE PRECISION | Tip amount |
| tolls_amount | DOUBLE PRECISION | Toll charges |
| improvement_surcharge | DOUBLE PRECISION | Improvement surcharge |
| total_amount | DOUBLE PRECISION | Total trip charge |
| congestion_surcharge | DOUBLE PRECISION | Congestion surcharge |
| airport_fee | DOUBLE PRECISION | Airport fee |
| cbd_congestion_fee | DOUBLE PRECISION | CBD congestion fee |
| source_file | VARCHAR(100) | Original Parquet filename |
| imported_at | TIMESTAMP WITH TIME ZONE | Import timestamp |

### 2.2 taxi_zone_lookup

**Grain:** One record per TLC taxi zone.

| Column | Data Type | Description |
|---|---|---|
| locationid | INTEGER | Unique taxi zone identifier |
| borough | VARCHAR(50) | Borough |
| zone | VARCHAR(100) | Taxi zone name |
| service_zone | VARCHAR(50) | Service zone classification |

### 2.3 import_manifest

**Grain:** One record per imported source file.

| Column | Data Type | Description |
|---|---|---|
| id | SERIAL | Manifest identifier |
| filename | VARCHAR(255) | Source filename |
| file_size_bytes | BIGINT | File size |
| parquet_row_count | BIGINT | Original Parquet row count |
| imported_row_count | BIGINT | Imported row count |
| import_status | VARCHAR(50) | Import status |
| started_at | TIMESTAMP WITH TIME ZONE | Import start |
| completed_at | TIMESTAMP WITH TIME ZONE | Import completion |
| execution_time_seconds | NUMERIC(10,2) | Import duration |
| checksum_md5 | VARCHAR(64) | File checksum |
| error_message | TEXT | Import error details |

---

## 3. Bronze Layer

The Bronze layer is a warehouse-owned copy of the source data.

It should preserve source values and types without applying business transformations.

### 3.1 bronze.yellow_taxi_trips

**Grain:** One row per source taxi trip.

**Primary Key:** `source_trip_id`

| Column | Data Type | Description |
|---|---|---|
| source_trip_id | BIGINT | Original source trip ID |
| vendorid | INTEGER | Provider ID |
| tpep_pickup_datetime | TIMESTAMP | Pickup timestamp |
| tpep_dropoff_datetime | TIMESTAMP | Dropoff timestamp |
| passenger_count | BIGINT | Passenger count |
| trip_distance | DOUBLE PRECISION | Trip distance |
| ratecodeid | BIGINT | Rate code |
| store_and_fwd_flag | VARCHAR(10) | Store-and-forward flag |
| pulocationid | INTEGER | Pickup zone ID |
| dolocationid | INTEGER | Dropoff zone ID |
| payment_type | BIGINT | Payment type |
| fare_amount | DOUBLE PRECISION | Base fare |
| extra | DOUBLE PRECISION | Extra charges |
| mta_tax | DOUBLE PRECISION | MTA tax |
| tip_amount | DOUBLE PRECISION | Tip |
| tolls_amount | DOUBLE PRECISION | Tolls |
| improvement_surcharge | DOUBLE PRECISION | Improvement surcharge |
| total_amount | DOUBLE PRECISION | Total trip charge |
| congestion_surcharge | DOUBLE PRECISION | Congestion surcharge |
| airport_fee | DOUBLE PRECISION | Airport fee |
| cbd_congestion_fee | DOUBLE PRECISION | CBD congestion fee |
| source_file | VARCHAR(100) | Source file |
| imported_at | TIMESTAMP WITH TIME ZONE | Import timestamp |

### 3.2 bronze.ref_location

**Grain:** One row per TLC taxi zone.

| Column | Data Type | Description |
|---|---|---|
| location_id | INTEGER | TLC location ID |
| borough | VARCHAR(50) | Borough |
| zone | VARCHAR(100) | Zone name |
| service_zone | VARCHAR(50) | Service zone |

Source: `nyc_taxi_source.taxi_zone_lookup`.

### 3.3 bronze.import_manifest

Optional copy of the source import manifest for warehouse-side traceability.

---

## 4. Silver Layer

The Silver layer contains validated, standardized, and enriched records.

### 4.1 silver.yellow_taxi_trips

**Grain:** One accepted record per source taxi trip.

**Primary Key:** `source_trip_id`

| Column | Suggested Data Type | Description |
|---|---|---|
| source_trip_id | BIGINT | Original source trip ID |
| vendor_id | SMALLINT / INTEGER | Standardized provider ID |
| pickup_datetime | TIMESTAMP | Pickup timestamp |
| dropoff_datetime | TIMESTAMP | Dropoff timestamp |
| passenger_count | INTEGER | Validated passenger count |
| trip_distance | NUMERIC(12,2) | Standardized distance |
| ratecode_id | SMALLINT / INTEGER | Rate code |
| store_and_fwd_flag | VARCHAR(10) | Standardized flag |
| pickup_location_id | INTEGER | Pickup location |
| dropoff_location_id | INTEGER | Dropoff location |
| payment_type_id | SMALLINT / INTEGER | Payment type |
| fare_amount | NUMERIC(12,2) | Fare |
| extra | NUMERIC(12,2) | Extra charges |
| mta_tax | NUMERIC(12,2) | MTA tax |
| tip_amount | NUMERIC(12,2) | Tip |
| tolls_amount | NUMERIC(12,2) | Tolls |
| improvement_surcharge | NUMERIC(12,2) | Improvement surcharge |
| total_amount | NUMERIC(12,2) | Total trip charge |
| congestion_surcharge | NUMERIC(12,2) | Congestion surcharge |
| airport_fee | NUMERIC(12,2) | Airport fee |
| cbd_congestion_fee | NUMERIC(12,2) | CBD congestion fee |
| source_file | VARCHAR(100) | Source file lineage |
| transformed_at | TIMESTAMP WITH TIME ZONE | Transformation timestamp |

Final types and validation rules must be agreed upon by the warehouse and ETL developers.

### 4.2 silver.ref_providers

Supplementary provider mapping not present in the source database.

| Column | Data Type | Description |
|---|---|---|
| vendor_id | SMALLINT / INTEGER | Provider ID (PK) |
| provider_name | VARCHAR(150) | Provider name |

Proposed mappings:

| vendor_id | provider_name |
|---:|---|
| 1 | Creative Mobile Technologies, LLC |
| 2 | Curb Mobility, LLC |
| 6 | Myle Technologies Inc |
| 7 | Helix |

### 4.3 silver.ref_ratecode

| Column | Data Type | Description |
|---|---|---|
| ratecode_id | SMALLINT / INTEGER | Rate code (PK) |
| ratecode | VARCHAR(100) | Rate description |

Proposed mappings:

| ratecode_id | ratecode |
|---:|---|
| 1 | Standard rate |
| 2 | JFK |
| 3 | Newark |
| 4 | Nassau or Westchester |
| 5 | Negotiated fare |
| 6 | Group ride |
| 99 | Null/unknown |

### 4.4 silver.ref_payment_type

| Column | Data Type | Description |
|---|---|---|
| type_id | SMALLINT / INTEGER | Payment type ID (PK) |
| payment_type | VARCHAR(100) | Payment description |

Proposed mappings:

| type_id | payment_type |
|---:|---|
| 0 | Flex Fare Trip |
| 1 | Credit Card |
| 2 | Cash |
| 3 | No charge |
| 4 | Dispute |
| 5 | Unknown |
| 6 | Voided trip |

**Reference data note:** These are proposed supplementary mappings. Verify IDs and descriptions against the applicable TLC documentation before production use. A literal code such as `99` is not equivalent to SQL NULL.

### 4.5 silver.ref_location

Standardized copy of the TLC taxi zone lookup.

| Column | Data Type | Description |
|---|---|---|
| location_id | INTEGER | TLC location ID |
| borough | VARCHAR(50) | Borough |
| zone | VARCHAR(100) | Zone |
| service_zone | VARCHAR(50) | Service zone |

---

## 5. Gold Layer — Star Schema

The Gold layer is optimized for analytical queries and OLAP operations.

### 5.1 gold.fact_yellow_taxi_trips

**Grain:** One row per taxi trip.

**Primary Key:** `trip_key`  
**Unique Lineage Key:** `source_trip_id`

| Column | Suggested Data Type | Description |
|---|---|---|
| trip_key | BIGINT | Warehouse fact key |
| source_trip_id | BIGINT | Source trip identifier |
| pickup_date_key | INTEGER | Pickup date FK |
| dropoff_date_key | INTEGER | Dropoff date FK |
| pickup_time_key | INTEGER | Pickup time FK |
| dropoff_time_key | INTEGER | Dropoff time FK |
| vendor_key | INTEGER | Provider dimension FK |
| pickup_location_key | INTEGER | Pickup location FK |
| dropoff_location_key | INTEGER | Dropoff location FK |
| payment_key | INTEGER | Payment dimension FK |
| ratecode_key | INTEGER | Rate-code dimension FK |
| passenger_count | INTEGER | Passenger count |
| trip_distance | NUMERIC | Trip distance |
| trip_duration_minutes | NUMERIC | Calculated trip duration |
| fare_amount | NUMERIC(12,2) | Fare |
| extra | NUMERIC(12,2) | Extra charges |
| mta_tax | NUMERIC(12,2) | MTA tax |
| tip_amount | NUMERIC(12,2) | Tip |
| tolls_amount | NUMERIC(12,2) | Tolls |
| improvement_surcharge | NUMERIC(12,2) | Improvement surcharge |
| total_amount | NUMERIC(12,2) | Total trip charge |
| congestion_surcharge | NUMERIC(12,2) | Congestion surcharge |
| airport_fee | NUMERIC(12,2) | Airport fee |
| cbd_congestion_fee | NUMERIC(12,2) | CBD congestion fee |

The fact table references Silver through `source_trip_id` for lineage. If a foreign key is implemented, it should reference `silver.yellow_taxi_trips(source_trip_id)`.

### 5.2 gold.dim_date

**Grain:** One row per calendar date.

| Column | Data Type | Description |
|---|---|---|
| date_key | INTEGER | YYYYMMDD primary key |
| full_date | DATE | Actual date |
| day | SMALLINT | Day of month |
| day_name | VARCHAR(10) | Day name |
| day_of_week | SMALLINT | Weekday number |
| week_of_year | SMALLINT | Week number |
| month | SMALLINT | Month number |
| month_name | VARCHAR(10) | Month name |
| quarter | SMALLINT | Calendar quarter |
| year | SMALLINT | Calendar year |
| is_weekend | BOOLEAN | Weekend indicator |

### 5.3 gold.dim_time

**Grain:** One row per time value at the selected precision.

| Column | Data Type | Description |
|---|---|---|
| time_key | INTEGER | HHMMSS primary key |
| full_time | TIME | Actual time |
| hour | SMALLINT | Hour |
| minute | SMALLINT | Minute |
| second | SMALLINT | Second |
| am_pm | VARCHAR(2) | AM or PM |
| time_period | VARCHAR(20) | Time classification |

Suggested time classifications:

| Time Range | Period |
|---|---|
| 00:00–04:59 | Late Night |
| 05:00–11:59 | Morning |
| 12:00–16:59 | Afternoon |
| 17:00–20:59 | Evening |
| 21:00–23:59 | Night |

The team must agree whether the time dimension uses second-level or minute-level precision. The `HHMMSS` key does not preserve fractional seconds.

### 5.4 gold.dim_vendor

| Column | Data Type | Description |
|---|---|---|
| vendor_key | INTEGER | Surrogate primary key |
| vendor_id | SMALLINT / INTEGER | Provider business key |
| vendor_name | VARCHAR(150) | Provider name |

### 5.5 gold.dim_location

| Column | Data Type | Description |
|---|---|---|
| location_key | INTEGER | Surrogate primary key |
| location_id | INTEGER | TLC location business key |
| borough | VARCHAR(50) | Borough |
| zone | VARCHAR(100) | Zone |
| service_zone | VARCHAR(50) | Service zone |

Used twice in the fact table for pickup and dropoff locations.

### 5.6 gold.dim_payment

| Column | Data Type | Description |
|---|---|---|
| payment_key | INTEGER | Surrogate primary key |
| payment_type_id | SMALLINT / INTEGER | Payment business key |
| payment_description | VARCHAR(100) | Payment description |

### 5.7 gold.dim_ratecode

| Column | Data Type | Description |
|---|---|---|
| ratecode_key | INTEGER | Surrogate primary key |
| ratecode_id | SMALLINT / INTEGER | Rate-code business key |
| ratecode_name | VARCHAR(100) | Rate-code description |

---

## 6. Relationships

The Gold fact table references:

- `dim_date` twice: pickup and dropoff.
- `dim_time` twice: pickup and dropoff.
- `dim_location` twice: pickup and dropoff.
- `dim_vendor`.
- `dim_payment`.
- `dim_ratecode`.

The fact table should have one record per accepted Silver trip.

Use an agreed Unknown dimension member for missing or unmapped IDs if the team chooses that approach. Do not use arbitrary foreign-key values.

---

## 7. Supported Analytical Questions

The warehouse is designed to answer:

1. How do total trip charges change monthly?
2. Which boroughs have the most pickups and dropoffs?
3. What are the busiest hours and days?
4. Which pickup-to-dropoff routes have the highest trip volume?
5. Which borough pairs generate the most trips?
6. How do average fares differ by rate code?
7. Which providers have the highest trip volume and total charges?
8. How do payment methods vary across boroughs?
9. How do trip distance and duration vary by time and location?
10. How does weekday demand compare with weekend demand?

**Terminology:** `total_amount` represents the total trip charge recorded in the source data. It should not automatically be interpreted as company net revenue or profit.

---

## 8. Design Decisions to Confirm

Before final ETL implementation, agree on:

- Final Silver data types and decimal precision.
- Validation and rejected-record handling.
- Provenance and version of supplementary reference mappings.
- Date range and week-number convention.
- Time dimension precision and fractional-second handling.
- Unknown dimension member strategy.
- Foreign-key and uniqueness constraints.
- Fact-table lineage and reload strategy.
