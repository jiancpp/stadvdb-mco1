
# ETL Handoff Checklist (to DataWarehouse)
## NYC Yellow Taxi Data Warehouse (2025)

**Source Database:** `nyc_taxi_source`  
**Target Database:** `DataWarehouse`  
**Dataset:** January–December 2025 NYC Yellow Taxi Trip Records

## 0. Setup

You may initialize the Data Warehouse locally for testing by running the SQL scripts in `warehouse/sql` sequentially.

Alternatively, you may access the initialized DataWarehouse through the shared ngrok tunnel. PostgreSQL must be running on the warehouse developer's machine.

### Shared Data Warehouse connection

| Setting | Value |
|---|---|
| Host | `0.tcp.ap.ngrok.io` |
| Port | `16989` |
| Database | `DataWarehouse` |
| Username | `dw_olap` |
| Password | Ask the Data Warehouse developer |

Keep credentials private. Do not commit passwords or connection strings containing passwords to the repository.

### Install dependencies

```bash
pip install -r requirements.txt
```

To validate your connection to the shared Data Warehouse, run this from the `etl/` module:

```bash
python connections.py
```

## 1. Understand the Data Warehouse

The warehouse has three layers. Your task is to move data through each layer.

| Layer | What you need to do |
|---|---|
| Bronze | Copy raw data from the source database |
| Silver | Clean, standardize, and enrich the data |
| Gold | Organize the data into fact and dimension tables for OLAP |

**Overall workflow:**

```text
SOURCE DATABASE
      |
      v
BRONZE
Raw data copied from source
      |
      v
SILVER
Cleaned and enriched data
      |
      v
GOLD
Fact table + Dimension tables
      |
      v
OLAP WEB APPLICATION
```



---

## 2. Source Database Checklist

Connect to `nyc_taxi_source` and retrieve the following tables:

- [ ] `yellow_tripdata_2025` — Main taxi trip records
- [ ] `taxi_zone_lookup` — Pickup and dropoff zone information
- [ ] `import_manifest` — Source file import information (if needed for auditing)

Important source columns:

| Column | Purpose |
|---|---|
| `trip_id` | Unique trip identifier |
| `vendorid` | Taxi provider |
| `tpep_pickup_datetime` | Pickup date and time |
| `tpep_dropoff_datetime` | Dropoff date and time |
| `passenger_count` | Number of passengers |
| `trip_distance` | Trip distance |
| `ratecodeid` | Rate code |
| `pulocationid` | Pickup zone |
| `dolocationid` | Dropoff zone |
| `payment_type` | Payment method |
| `total_amount` | Total trip charge |

**Important:** Preserve `trip_id` throughout the ETL process as `source_trip_id`. This allows us to trace every warehouse record back to its original source.

---

## 3. Load Data into Bronze

**Goal:** Copy the source data into the warehouse without changing its original values.

Target tables:

- [ ] `bronze.yellow_taxi_trips`
- [ ] `bronze.ref_location`
- [ ] `bronze.import_manifest` (optional)

Tasks:

- [ ] Connect to the source and target databases.
- [ ] Extract all 2025 taxi trip records.
- [ ] Copy the trip records into `bronze.yellow_taxi_trips`.
- [ ] Map source `trip_id` to Bronze `source_trip_id`.
- [ ] Copy `taxi_zone_lookup` into `bronze.ref_location`.
- [ ] Preserve original values, nulls, and data types.
- [ ] Retain `source_file` and `imported_at`.
- [ ] Check that source and Bronze row counts match.
- [ ] Prevent duplicate records when the ETL process is rerun.

**Expected result:** Bronze contains a raw warehouse copy of the source data.

---

## 4. Transform Data into Silver

**Goal:** Clean and standardize the Bronze data so it is ready for analysis.

Target tables:

- [ ] `silver.yellow_taxi_trips`
- [ ] `silver.ref_location`
- [ ] `silver.ref_providers`
- [ ] `silver.ref_ratecode`
- [ ] `silver.ref_payment_type`

### A. Clean and standardize trip records

- [ ] Rename columns to consistent `snake_case`.
- [ ] Standardize data types where appropriate.
- [ ] Check for missing pickup and dropoff timestamps.
- [ ] Check for invalid trip durations.
- [ ] Check for invalid passenger counts and trip distances.
- [ ] Check for unusual fare and payment values.
- [ ] Identify duplicate `source_trip_id` values.
- [ ] Retain the original `source_trip_id`.
- [ ] Keep rejected records with their rejection reasons instead of silently deleting them.

Agree on validation rules before rejecting records. Unusual values should not automatically be discarded.

### B. Load supplementary reference data

The source database does not contain provider names, rate-code descriptions, or payment descriptions.

Load these mappings into Silver:

**`silver.ref_providers`**

| vendor_id | provider_name |
|---:|---|
| 1 | Creative Mobile Technologies, LLC |
| 2 | Curb Mobility, LLC |
| 6 | Myle Technologies Inc |
| 7 | Helix |

**`silver.ref_ratecode`**

| ratecode_id | ratecode |
|---:|---|
| 1 | Standard rate |
| 2 | JFK |
| 3 | Newark |
| 4 | Nassau or Westchester |
| 5 | Negotiated fare |
| 6 | Group ride |
| 99 | Null/unknown |

**`silver.ref_payment_type`**

| type_id | payment_type |
|---:|---|
| 0 | Flex Fare Trip |
| 1 | Credit Card |
| 2 | Cash |
| 3 | No charge |
| 4 | Dispute |
| 5 | Unknown |
| 6 | Voided trip |

- [ ] Verify reference descriptions against applicable TLC documentation.
- [ ] Document where the reference data came from.
- [ ] Load the reference tables before enriching trip records.
- [ ] Join reference tables to trip records using their IDs.
- [ ] Report IDs that do not have matching descriptions.

Use `LEFT JOIN` so unmatched reference IDs do not cause trips to disappear.

**Expected result:** Silver contains standardized trips and the reference information needed to interpret them.

---

## 5. Load Data into Gold

**Goal:** Convert Silver records into a star schema for OLAP analysis.

### A. Populate dimension tables first

Load these tables before the fact table:

- [ ] `gold.dim_date`
- [ ] `gold.dim_time`
- [ ] `gold.dim_vendor`
- [ ] `gold.dim_location`
- [ ] `gold.dim_payment`
- [ ] `gold.dim_ratecode`

What each dimension contains:

| Dimension | Information |
|---|---|
| `dim_date` | Calendar details: day, month, quarter, year |
| `dim_time` | Hour, minute, second, AM/PM, time period |
| `dim_vendor` | Taxi provider names |
| `dim_location` | Boroughs, zones, service zones |
| `dim_payment` | Payment method descriptions |
| `dim_ratecode` | Rate-code descriptions |

Additional requirements:

- [ ] Generate the 2025 calendar dates.
- [ ] Populate the time dimension using the agreed precision.
- [ ] Use surrogate keys for Gold dimensions.
- [ ] Avoid duplicate dimension records.
- [ ] Handle missing or unknown dimension values consistently.

### B. Populate the fact table

Target: `gold.fact_yellow_taxi_trips`

**Grain:** One row per accepted taxi trip.

- [ ] Read accepted records from `silver.yellow_taxi_trips`.
- [ ] Retrieve the appropriate dimension keys.
- [ ] Map pickup and dropoff dates.
- [ ] Map pickup and dropoff times.
- [ ] Map pickup and dropoff locations.
- [ ] Map vendor, payment, and rate code.
- [ ] Calculate trip duration in minutes.
- [ ] Insert measures and monetary values.
- [ ] Preserve `source_trip_id`.
- [ ] Prevent duplicate fact records.

Measures to include:

- Passenger count
- Trip distance
- Trip duration
- Fare amount
- Extra charges
- MTA tax
- Tip amount
- Tolls
- Improvement surcharge
- Total amount
- Congestion surcharge
- Airport fee
- CBD congestion fee

**Expected result:** Every accepted Silver trip has a corresponding Gold fact record with valid dimension references.

---

## 6. Test and Validate the ETL Pipeline

Before considering the ETL complete, verify the following:

### Data Completeness

- [ ] Source row count is recorded.
- [ ] Bronze row count matches extracted source records.
- [ ] Silver accepted and rejected row counts are recorded.
- [ ] Gold fact count reconciles with accepted Silver records.

### Data Quality

- [ ] No duplicate `source_trip_id` values.
- [ ] No unexplained missing dimension references.
- [ ] No foreign-key violations.
- [ ] Unmatched reference IDs are reported.
- [ ] Invalid records have documented rejection reasons.

### ETL Reliability

- [ ] Pipeline can run from beginning to end.
- [ ] Running it again does not create duplicate records.
- [ ] Failed loads produce useful error messages.
- [ ] Load execution time is recorded.
- [ ] Monthly source files can be tracked.

---

## 7. Prepare for OLAP Integration

Once Gold is populated:

- [ ] Verify all Gold dimensions and fact records.
- [ ] Test analytical SQL queries.
- [ ] Provide the OLAP/backend developer with the Gold schema.
- [ ] Confirm the backend can connect to PostgreSQL.
- [ ] Provide read-only database access for OLAP.
- [ ] Ensure the frontend accesses data through the backend API, not directly through PostgreSQL.

The warehouse should support questions such as:

1. What is the monthly trip volume and total trip charges?
2. Which boroughs have the most pickups?
3. What are the busiest hours?
4. Which pickup-to-dropoff routes are most common?
5. Which providers have the highest trip volume?
6. What payment methods are most frequently used?
7. How do average fares differ by rate code?

---

## 8. Final ETL Deliverables

Before handing the ETL implementation back to the team, provide:

- [ ] Working ETL scripts or pipeline.
- [ ] Source-to-target column mappings.
- [ ] Data cleaning and validation rules.
- [ ] Reference data loading scripts.
- [ ] Rejected-record handling.
- [ ] ETL execution logs.
- [ ] Source, Bronze, Silver, and Gold row-count reports.
- [ ] Evidence that the pipeline runs successfully.
- [ ] Sample analytical queries against Gold.

---

## 9. Important Agreements with the Warehouse Developer

Confirm these before final implementation:

| Item | Decision to confirm |
|---|---|
| Trip identifier | Use `source_trip_id` across layers |
| Silver data types | Agree on final numeric precision and integer types |
| Invalid records | Keep rejected records and rejection reasons |
| Reference data | Verify TLC mappings and document their sources |
| Time dimension | Decide between second-level and minute-level precision |
| Unknown values | Agree on how missing dimension values are represented |
| Duplicate handling | Use a repeatable upsert or reload strategy |
| Fact table grain | One row per accepted taxi trip |

**Reminder:** Do not independently change warehouse table names, column names, or data types. Coordinate schema changes with the Data Warehouse developer first.
