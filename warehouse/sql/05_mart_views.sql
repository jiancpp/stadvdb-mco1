-- =====================================================================================
-- Rollups for the "NYC Taxi Opportunities & Efficiency" dashboard.
-- gold.fact_yellow_taxi_trips has ~48M rows, so the API never scans it: every dashboard
-- query reads the small materialized views below (a few thousand to ~1M rows each).
--
-- ASSUMED column names (change here if yours differ):
--   gold.dim_date.date_key, gold.dim_location.location_key, gold.dim_time."hour"
-- Rows with trip_duration_minutes <= 0 are excluded so every "per occupied hour"
-- ratio uses the same row set.
-- Run once, then REFRESH after each ETL load (bottom of file).
-- =====================================================================================

CREATE SCHEMA IF NOT EXISTS mart;

-- 1) pickup zone x day x trip-length band
--    feeds: KPI cards, where-to-be bubbles, trip length, monthly demand
--    band: 1 <1mi | 2 1-2mi | 3 2-4mi | 4 4-10mi | 5 10+mi
DROP MATERIALIZED VIEW IF EXISTS mart.agg_pickup_zone_day_band CASCADE;
CREATE MATERIALIZED VIEW mart.agg_pickup_zone_day_band AS
SELECT f.pickup_date_key     AS date_key,
       f.pickup_location_key AS location_key,
       (CASE WHEN f.trip_distance < 1  THEN 1
             WHEN f.trip_distance < 2  THEN 2
             WHEN f.trip_distance < 4  THEN 3
             WHEN f.trip_distance < 10 THEN 4
             ELSE 5 END)::smallint AS length_band,
       COUNT(*)::bigint                            AS trips,
       SUM(f.total_amount)::numeric(18,2)          AS revenue,
       SUM(f.trip_duration_minutes)::numeric(18,2) AS duration_min,
       SUM(f.trip_distance)::numeric(18,2)         AS distance_mi
FROM gold.fact_yellow_taxi_trips f
WHERE f.trip_duration_minutes > 0
GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX ux_agg_pzdb ON mart.agg_pickup_zone_day_band (date_key, location_key, length_band);

-- 2) dropoffs per zone per day  (net flow = dropoffs - pickups)
DROP MATERIALIZED VIEW IF EXISTS mart.agg_dropoff_zone_day CASCADE;
CREATE MATERIALIZED VIEW mart.agg_dropoff_zone_day AS
SELECT f.dropoff_date_key     AS date_key,
       f.dropoff_location_key AS location_key,
       COUNT(*)::bigint       AS trips
FROM gold.fact_yellow_taxi_trips f
WHERE f.trip_duration_minutes > 0
GROUP BY 1, 2;
CREATE UNIQUE INDEX ux_agg_dzd ON mart.agg_dropoff_zone_day (date_key, location_key);

-- 3) pickup borough x day x hour of day   (feeds slow windows: speed vs yield)
--    pickup_time_key is HHMMSS, so hour = key / 10000
DROP MATERIALIZED VIEW IF EXISTS mart.agg_borough_day_hour CASCADE;
CREATE MATERIALIZED VIEW mart.agg_borough_day_hour AS
SELECT f.pickup_date_key                         AS date_key,
       COALESCE(l.borough, 'Unknown')            AS borough,
       ((f.pickup_time_key::int) / 10000)::smallint AS hour,
       COUNT(*)::bigint                            AS trips,
       SUM(f.total_amount)::numeric(18,2)          AS revenue,
       SUM(f.trip_duration_minutes)::numeric(18,2) AS duration_min,
       SUM(f.trip_distance)::numeric(18,2)         AS distance_mi
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_location l ON l.location_key = f.pickup_location_key
WHERE f.trip_duration_minutes > 0
GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX ux_agg_bdh ON mart.agg_borough_day_hour (date_key, borough, hour);

-- hour -> time_period lookup (Morning / Afternoon / Evening / Night / Late Night)
CREATE OR REPLACE VIEW mart.hour_period AS
SELECT t."hour" AS hour, MIN(t.time_period) AS time_period
FROM gold.dim_time t
GROUP BY t."hour";

-- 4) corridor (pickup zone -> dropoff zone) x month x weekend flag
--    month grain keeps this ~1M rows; the corridors card snaps the date range to whole months
DROP MATERIALIZED VIEW IF EXISTS mart.agg_corridor_month CASCADE;
CREATE MATERIALIZED VIEW mart.agg_corridor_month AS
SELECT (f.pickup_date_key / 100)::int  AS month_key,          -- YYYYMM
       d.is_weekend::boolean           AS is_weekend,
       f.pickup_location_key           AS pickup_location_key,
       f.dropoff_location_key          AS dropoff_location_key,
       COUNT(*)::bigint                            AS trips,
       SUM(f.total_amount)::numeric(18,2)          AS revenue,
       SUM(f.trip_duration_minutes)::numeric(18,2) AS duration_min
FROM gold.fact_yellow_taxi_trips f
JOIN gold.dim_date d ON d.date_key = f.pickup_date_key
WHERE f.trip_duration_minutes > 0
GROUP BY 1, 2, 3, 4;
CREATE UNIQUE INDEX ux_agg_cm ON mart.agg_corridor_month (month_key, is_weekend, pickup_location_key, dropoff_location_key);

ANALYZE mart.agg_pickup_zone_day_band;
ANALYZE mart.agg_dropoff_zone_day;
ANALYZE mart.agg_borough_day_hour;
ANALYZE mart.agg_corridor_month;

-- ---- after every ETL load -------------------------------------------------------------
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mart.agg_pickup_zone_day_band;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mart.agg_dropoff_zone_day;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mart.agg_borough_day_hour;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mart.agg_corridor_month;

-- ---- sanity check: rollup totals must equal the fact table ----------------------------
-- SELECT (SELECT SUM(trips) FROM mart.agg_pickup_zone_day_band) AS rolled_up,
--        (SELECT COUNT(*) FROM gold.fact_yellow_taxi_trips WHERE trip_duration_minutes > 0) AS in_fact;
