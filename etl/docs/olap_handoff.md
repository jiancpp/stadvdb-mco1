# OLAP Handoff (from the Data Warehouse)

## NYC Yellow Taxi Data Warehouse (2025)

**Source database:** `nyc_taxi_source`
**Target database:** `DataWarehouse`
**Dataset:** January–December 2025 NYC Yellow Taxi Trip Records

This document is for the team building the OLAP backend and dashboard. It explains how to connect to the warehouse, what the Gold layer contains, what to watch out for when defining metrics, and what the application is expected to do. The ETL that loads the warehouse is documented separately in `etl_documentation.md`.

---

## 0. Setup

You may initialize the Data Warehouse locally for testing by running the SQL scripts in `warehouse/sql` sequentially (see the project `README.md`; the first script is destructive). A locally initialized warehouse is empty until the ETL has been run against it.

Alternatively, you may access the initialized Data Warehouse through the shared ngrok tunnel. PostgreSQL and the tunnel must be running on the warehouse developer's machine.

### Shared Data Warehouse connection

| Setting  | Value                                |
|----------|--------------------------------------|
| Host     | `0.tcp.ap.ngrok.io`                  |
| Port     | `16989`                              |
| Database | `DataWarehouse`                      |
| Username | `dw_olap` (read-only)                |
| Password | Ask the Data Warehouse developer     |

> **The ngrok port changes whenever the tunnel is restarted.** If you cannot connect, ask the warehouse developer for the current host and port.

> **Note:** Keep credentials private. Do not commit passwords or connection strings containing passwords to the repository.

### Install dependencies

```bash
pip install -r requirements.txt
```

Then create your `.env` from `.env.example`. For OLAP use:

- set `IS_ETL_DEVELOPER=0` (you do not need the source database),
- fill in the `WAREHOUSE_DB_*` variables with the ngrok host, port, user and password above.

To validate your connection to the shared Data Warehouse, run this from the project root:

```bash
python connections.py
```

---

## 1. Understand the Data Warehouse

The warehouse has three layers. The ETL moves data through them; **your application reads only the Gold layer.**

| Layer  | Contents                                                         | Used by OLAP? |
|--------|------------------------------------------------------------------|---------------|
| Bronze | Raw copy of the source data                                      | No            |
| Silver | Cleaned and standardized trips (plus rejected trips)             | No            |
| Gold   | Star schema: one fact table and six dimensions, built for OLAP   | **Yes**       |

### Overall workflow

```text
SOURCE DATABASE
      |
      v
BRONZE        Raw data copied from source
      |
      v
SILVER        Cleaned and standardized data (invalid trips rejected)
      |
      v
GOLD          Fact table + dimension tables
      |
      v
BACKEND API  -->  OLAP WEB APPLICATION
```

### ERD for Star Schema

![Star Schema ERD](Star_Schema_ERD.png)

### What was loaded (fill in after the full ETL run)

| Item | Value |
|---|---|
| Trips in `gold.fact_yellow_taxi_trips` | |
| Trips rejected during cleaning (not in Gold) | |
| Last full ETL run | |

---

## 2. Gold schema reference

### Tables

| Table | Grain | Rows | Key |
|---|---|---|---|
| `gold.fact_yellow_taxi_trips` | One row per accepted taxi trip | tens of millions | `trip_key` (also `bronze_trip_id`, unique) |
| `gold.dim_date` | One row per calendar date, 2025-01-01 to 2026-01-01 | 366 | `date_key` (`YYYYMMDD`) |
| `gold.dim_time` | One row per second of the day | 86,400 | `time_key` (`HHMMSS`) |
| `gold.dim_vendor` | One row per taxi provider | 4 + Unknown | `vendor_key` |
| `gold.dim_location` | One row per TLC taxi zone | 265 + Unknown | `location_key` |
| `gold.dim_payment` | One row per payment type | 7 | `payment_key` |
| `gold.dim_ratecode` | One row per rate code | 7 | `ratecode_key` |

### Fact table columns

| Group | Columns |
|---|---|
| Keys | `trip_key`, `bronze_trip_id` |
| Date / time | `pickup_date_key`, `dropoff_date_key`, `pickup_time_key`, `dropoff_time_key` |
| Dimensions | `vendor_key`, `pickup_location_key`, `dropoff_location_key`, `payment_key`, `ratecode_key` |
| Trip measures | `passenger_count`, `trip_distance` (miles), `trip_duration_minutes` |
| Charge measures | `fare_amount`, `extra`, `mta_tax`, `tip_amount`, `tolls_amount`, `improvement_surcharge`, `congestion_surcharge`, `airport_fee`, `cbd_congestion_fee`, `total_amount` |

### Dimension columns you will group and filter by

| Dimension | Useful columns |
|---|---|
| `dim_date` | `full_date`, `year`, `quarter`, `month`, `month_name`, `day`, `day_name`, `day_of_week` (1 = Monday), `week_of_year`, `is_weekend` |
| `dim_time` | `hour` (0–23), `minute`, `am_pm`, `time_period` (Late Night, Morning, Afternoon, Evening, Night) |
| `dim_vendor` | `vendor_id`, `vendor_name` |
| `dim_location` | `location_id`, `borough`, `location_zone`, `service_zone` |
| `dim_payment` | `payment_type_id`, `payment_description` |
| `dim_ratecode` | `ratecode_id`, `ratecode_name` |

### Joins

```text
fact.pickup_date_key     -> dim_date.date_key
fact.dropoff_date_key    -> dim_date.date_key
fact.pickup_time_key     -> dim_time.time_key
fact.dropoff_time_key    -> dim_time.time_key
fact.vendor_key          -> dim_vendor.vendor_key
fact.pickup_location_key -> dim_location.location_key   (alias as pickup)
fact.dropoff_location_key-> dim_location.location_key   (alias as dropoff)
fact.payment_key         -> dim_payment.payment_key
fact.ratecode_key        -> dim_ratecode.ratecode_key
```

`dim_date`, `dim_time` and `dim_location` are each used **twice** (pickup and dropoff), so join them with two different aliases when a query needs both.

### Hierarchies for roll-up and drill-down

- **Date:** year → quarter → month → day
- **Location:** borough → zone (and `service_zone` as a separate grouping)
- **Time of day:** `time_period` → hour

---

## 3. Data notes: read before defining metrics

**Coverage**
- Every trip has a **pickup in 2025** (2025-01-01 to 2025-12-31). Dropoffs can fall on 2026-01-01 for trips that run past midnight on New Year's Eve.
- Gold contains only trips that passed cleaning. Trips with impossible or implausible values (bad timestamps, zero or negative duration, extreme distance or speed, and so on) are excluded; the counts are in the table in section 1.

**Money**
- `total_amount` is the total charged to the passenger. It **does not include cash tips**, and it is **not company revenue or profit**. Label it "Total charges" in the UI.
- `fare_amount` is the metered fare only. Do not use it interchangeably with `total_amount`.
- **Negative amounts are kept** (cancellations, disputes, refunds). `SUM(total_amount)` is therefore a net figure. For averages such as "average fare", decide as a team whether to include or exclude negative and zero fares, and state the definition on the dashboard.
- `tip_amount` is only recorded for credit-card payments. Tip analysis is only meaningful when filtered to the credit-card payment type.
- Surcharge columns are never NULL (missing values were set to 0). `cbd_congestion_fee` is 0 for the first days of January because it only began on January 5, 2025.

**Unknown and missing values**
- **Payment:** unknown or missing payment types appear as the official TLC type **5 – Unknown**.
- **Rate code:** unknown or missing rate codes appear as the official TLC code **99 – Null/unknown**.
- **Location:** a missing or unmapped zone appears as the **Unknown** member (`location_key = -1`, borough and zone shown as `Unknown`). Show it as its own category or filter it out deliberately; do not drop it silently.
- `passenger_count` and `trip_distance` can be **NULL** (aggregates such as `AVG` ignore NULLs). A `passenger_count` of 0 is possible. Show unavailable data differently from a real zero.

**Time and calendar conventions**
- `day_of_week` is ISO (1 = Monday … 7 = Sunday). `week_of_year` is the ISO week number. `is_weekend` is Saturday and Sunday.
- Time is stored to the second; fractional seconds are dropped.

**Comparisons**
- Weekdays and weekends have different numbers of days. Compare **average trips per day**, not raw totals, when contrasting them.

**Size and performance**
- The fact table has tens of millions of rows and the warehouse is reached over a tunnel. Always aggregate in SQL, filter on dates where possible, and avoid returning raw trip rows.
- The Gold DDL does not create indexes on the fact table's foreign-key columns. If queries are slow, ask the warehouse developer to add them (see Appendix B).

---

## 4. Example queries

Each answers one of the supported analytical questions. All use only Gold tables.

**Monthly trips and total charges**

```sql
SELECT d.year, d.month, d.month_name,
       COUNT(*)            AS trips,
       SUM(f.total_amount) AS total_charges
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_date d ON d.date_key = f.pickup_date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;
```

**Pickups by borough**

```sql
SELECT l.borough, COUNT(*) AS pickups
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_location l ON l.location_key = f.pickup_location_key
GROUP BY l.borough
ORDER BY pickups DESC;
```

**Busiest pickup hours**

```sql
SELECT t.hour, COUNT(*) AS trips
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_time t ON t.time_key = f.pickup_time_key
GROUP BY t.hour
ORDER BY t.hour;
```

**Most common routes (top 20)**

```sql
SELECT pl.location_zone AS pickup_zone,
       dl.location_zone AS dropoff_zone,
       COUNT(*)         AS trips
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_location pl ON pl.location_key = f.pickup_location_key
JOIN gold.dim_location dl ON dl.location_key = f.dropoff_location_key
GROUP BY pl.location_zone, dl.location_zone
ORDER BY trips DESC
LIMIT 20;
```

**Average fare by rate code**

```sql
SELECT r.ratecode_name,
       COUNT(*)                   AS trips,
       ROUND(AVG(f.fare_amount), 2) AS avg_fare
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_ratecode r ON r.ratecode_key = f.ratecode_key
GROUP BY r.ratecode_name
ORDER BY trips DESC;
```

**Trips and total charges by provider**

```sql
SELECT v.vendor_name, COUNT(*) AS trips, SUM(f.total_amount) AS total_charges
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_vendor v ON v.vendor_key = f.vendor_key
GROUP BY v.vendor_name
ORDER BY trips DESC;
```

**Payment methods by borough**

```sql
SELECT l.borough, p.payment_description, COUNT(*) AS trips
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_location l ON l.location_key = f.pickup_location_key
JOIN gold.dim_payment  p ON p.payment_key  = f.payment_key
GROUP BY l.borough, p.payment_description
ORDER BY l.borough, trips DESC;
```

**Weekday vs weekend (average trips per day)**

```sql
SELECT d.is_weekend,
       COUNT(*)                                   AS trips,
       COUNT(DISTINCT d.date_key)                 AS days,
       ROUND(COUNT(*)::NUMERIC / COUNT(DISTINCT d.date_key), 0) AS avg_trips_per_day
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_date d ON d.date_key = f.pickup_date_key
GROUP BY d.is_weekend;
```

---

## 5. OLAP Integration

Once Gold is populated:

- [ ] Confirm the backend can connect to PostgreSQL.
- [ ] Use read-only database access for OLAP.
- [ ] Create a frontend that accesses data through the backend API, not directly through PostgreSQL.

The warehouse supports questions such as:

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

---

## 6. Backend Development: Query APIs

**Goal:** Develop backend endpoints that retrieve, filter, group, and aggregate Gold data for the frontend. The backend is the only application component that should connect directly to PostgreSQL.

### A. Database Integration

- [ ] Configure PostgreSQL connection using environment variables.
- [ ] Use the `dw_olap` read-only account.
- [ ] Restrict queries to the Gold schema.
- [ ] Use parameterized SQL queries or a safe query builder.
- [ ] Implement connection pooling where appropriate.
- [ ] Handle database connection failures and timeouts (the warehouse is reached through an ngrok tunnel and may be unavailable).
- [ ] Avoid exposing database credentials and internal SQL errors.

### B. Recommended API Endpoints

The following are suggested endpoints. Final routes and response structures should be agreed upon by the team.

| Endpoint                                  | Purpose                                           |
|-------------------------------------------|---------------------------------------------------|
| `GET /api/overview/kpis`                  | Retrieve dashboard summary metrics                |
| `GET /api/analytics/trips-over-time`      | Retrieve trip volume over time                    |
| `GET /api/analytics/revenue-over-time`    | Retrieve total charges over time                  |
| `GET /api/analytics/trips-by-borough`     | Retrieve trip counts by borough                   |
| `GET /api/analytics/trips-by-hour`        | Retrieve trip counts by hour                      |
| `GET /api/analytics/top-routes`           | Retrieve the most common pickup-to-dropoff routes |
| `GET /api/analytics/trips-by-vendor`      | Retrieve trip counts by taxi provider             |
| `GET /api/analytics/payment-distribution` | Retrieve payment method distribution              |
| `GET /api/analytics/fares-by-ratecode`    | Retrieve fare statistics by rate code             |
| `GET /api/filters`                        | Retrieve available filter options                 |

### C. API Query Requirements

- [ ] Query only Gold tables or approved Gold views.
- [ ] Join fact and dimension tables using their established relationships (section 2).
- [ ] Support date-range filtering.
- [ ] Support borough and location filtering.
- [ ] Support vendor filtering.
- [ ] Support payment method filtering.
- [ ] Support rate-code filtering.
- [ ] Support grouping by day, month, quarter, and year where applicable.
- [ ] Return aggregated results instead of unnecessary raw records.
- [ ] Validate query parameters.
- [ ] Implement pagination for endpoints returning large lists.
- [ ] Use consistent JSON response structures.
- [ ] Provide meaningful error responses.
- [ ] Document API routes, parameters, and response formats.

### D. Suggested Dashboard KPIs

Agree on metric definitions before implementation (see the data notes in section 3).

| KPI                     | Suggested Calculation            |
|-------------------------|----------------------------------|
| Total Trips             | `COUNT` of fact records          |
| Total Revenue / Charges | `SUM` of `total_amount`          |
| Average Fare            | `AVG` of `fare_amount`           |
| Average Trip Distance   | `AVG` of `trip_distance`         |
| Average Trip Duration   | `AVG` of `trip_duration_minutes` |
| Average Passengers      | `AVG` of `passenger_count`       |

> **Be explicit about monetary measures.** `fare_amount` and `total_amount` are not interchangeable, and `total_amount` is total charges, not revenue.

---

## 7. Frontend Development: Dashboard and Analytics

**Goal:** Develop an interactive dashboard that allows users to explore and analyze NYC Yellow Taxi trip data. The frontend must retrieve data through backend APIs. It must never connect directly to PostgreSQL.

### A. Dashboard Overview

Create an overview dashboard containing:

- [ ] Total Trips
- [ ] Total Revenue / Charges
- [ ] Average Fare
- [ ] Average Trip Distance
- [ ] Average Trip Duration
- [ ] Trip Volume Over Time

Use KPI cards for summary metrics and charts for analytical trends.

### B. Analytics and Visualizations

| Analysis                   | Suggested Visualization    |
|----------------------------|----------------------------|
| Trip Volume Over Time      | Line or Area Chart         |
| Total Charges Over Time    | Line or Area Chart         |
| Trips by Borough           | Bar Chart                  |
| Busiest Pickup Hours       | Bar Chart                  |
| Most Common Routes         | Ranked Bar Chart or Table  |
| Trips by Provider          | Bar or Donut Chart         |
| Payment Distribution       | Donut or Bar Chart         |
| Average Fares by Rate Code | Bar Chart                  |

Charts should include:

- Descriptive titles
- Axis labels
- Units of measurement
- Legends where appropriate
- Tooltips for detailed values
- Readable date and number formatting

### C. Interactive Filters

Implement dashboard filters such as:

- [ ] Date Range
- [ ] Borough / Location
- [ ] Vendor
- [ ] Payment Method
- [ ] Rate Code

Additional requirements:

- [ ] Allow users to combine filters.
- [ ] Update relevant KPI cards and charts when filters change.
- [ ] Provide a reset filters option.
- [ ] Display currently active filters.
- [ ] Show loading indicators while retrieving data.
- [ ] Show appropriate empty states when no records match.
- [ ] Display useful error messages when API requests fail.

> The frontend should pass filter selections to backend APIs. It should not independently calculate warehouse-wide aggregations from raw trip records.

### D. User Experience

- [ ] Use a consistent dashboard layout.
- [ ] Make charts readable on desktop and mobile.
- [x] Provide clear navigation between overview and analytics.
- [ ] Use consistent colors and visual hierarchy.
- [ ] Display metric definitions where necessary.
- [ ] Distinguish unavailable data from actual zero values.
- [ ] Ensure responsive layouts.

---

## 8. OLAP Operations

The application should support the fundamental OLAP operations.

| Operation  | Example                                           |
|------------|---------------------------------------------------|
| Roll-up    | View trip volume by month instead of by day       |
| Drill-down | Select a month to inspect daily trip volume       |
| Slice      | View trips for a selected year or payment type    |
| Dice       | Filter trips by date range, borough, and vendor   |
| Pivot      | Compare trip volume across boroughs and months    |

### Implementation Requirements

- [ ] Identify which APIs support each operation.
- [ ] Allow users to change aggregation levels (use the hierarchies in section 2).
- [ ] Allow users to drill down into more detailed data.
- [ ] Support multiple simultaneous filters.
- [ ] Support comparisons across dimensions.
- [ ] Ensure results remain consistent with Gold data.

---

## Appendix A: Read-only account (for the warehouse developer)

The OLAP application should connect as a read-only role limited to the Gold schema. Create it once on the warehouse server (use a real password, and do not commit it):

```sql
CREATE ROLE dw_olap LOGIN PASSWORD '<choose-a-strong-password>';
GRANT CONNECT ON DATABASE "DataWarehouse" TO dw_olap;
GRANT USAGE   ON SCHEMA gold TO dw_olap;
GRANT SELECT  ON ALL TABLES IN SCHEMA gold TO dw_olap;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO dw_olap;
ALTER ROLE dw_olap SET statement_timeout = '60s';
```

Notes:

- The role is created at the server level, but `01_create_schemas.sql` drops and recreates the database, which removes the grants. **Rerun the `GRANT` statements after any rebuild.**
- Do not grant access to the `bronze` or `silver` schemas.
- Only share the ngrok tunnel while the OLAP team needs it.

## Appendix B: Analytics views and performance (for the warehouse developer)

- `warehouse/sql/05_analytics_views.sql` is currently **empty**, so there are no approved Gold views yet. Until views exist, the backend should query the Gold tables directly (section 4 has starting queries). If the team wants views, add them to `05` and list them here.
- The fact table has a primary key and a unique key on `bronze_trip_id`, but no indexes on its foreign-key columns. If dashboard queries are slow, create indexes **after the data load**, selectively, because each index on tens of millions of rows takes gigabytes:

```sql
CREATE INDEX IF NOT EXISTS ix_fact_pickup_date     ON gold.fact_yellow_taxi_trips (pickup_date_key);
CREATE INDEX IF NOT EXISTS ix_fact_pickup_location ON gold.fact_yellow_taxi_trips (pickup_location_key);
CREATE INDEX IF NOT EXISTS ix_fact_pickup_time     ON gold.fact_yellow_taxi_trips (pickup_time_key);
CREATE INDEX IF NOT EXISTS ix_fact_payment         ON gold.fact_yellow_taxi_trips (payment_key);
CREATE INDEX IF NOT EXISTS ix_fact_ratecode        ON gold.fact_yellow_taxi_trips (ratecode_key);
CREATE INDEX IF NOT EXISTS ix_fact_vendor          ON gold.fact_yellow_taxi_trips (vendor_key);
```

- For heavy dashboard aggregates (monthly totals, trips by hour), consider materialized views that the ETL refreshes after each load.