-- 1. Distinct Boroughs and Date Bounds
-- 1a. SQL_BOROUGHS: Get list of distinct boroughs
EXPLAIN ANALYZE
SELECT DISTINCT borough 
FROM gold.dim_location
WHERE location_key <> -1 
  AND borough IS NOT NULL 
ORDER BY 1;

-- 1b. SQL_BOUNDS: Date key range available in the pickup rollup
EXPLAIN ANALYZE
SELECT 
    MIN(date_key) AS lo, 
    MAX(date_key) AS hi 
FROM mart.agg_pickup_zone_day_band;


-- 2. KPI Cards (Monthly, Daily, Q1 Baseline)
-- Parameters:
-- $1 = start (YYYYMMDD integer, e.g. 20250101)
-- $2 = end   (YYYYMMDD integer, e.g. 20251231)
-- $3 = day_type ('all', 'weekday', or 'weekend')
-- $4 = borough (Borough name or NULL)

-- 2a. SQL_KPI_MONTHLY
PREPARE stmt_kpi_monthly (int, int, text, text) AS
SELECT 
    d.year, 
    d.month, 
    SUM(a.trips) AS trips, 
    SUM(a.revenue) AS revenue,
    SUM(a.duration_min) AS duration_min, 
    SUM(a.distance_mi) AS distance_mi
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d ON d.date_key = a.date_key
JOIN gold.dim_location l ON l.location_key = a.location_key
WHERE a.date_key BETWEEN $1 AND $2
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
  AND ($4 IS NULL OR l.borough = $4)
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;

EXPLAIN ANALYZE
EXECUTE stmt_kpi_monthly(20250101, 20251231, 'all', NULL);

-- Optimized ========================================================
DEALLOCAtE stmt_kpi_monthly;


PREPARE stmt_kpi_monthly (int, int, text, text) AS
SELECT
    d.year,
    d.month,
    SUM(a.trips) AS trips,
    SUM(a.revenue) AS revenue,
    SUM(a.duration_min) AS duration_min,
    SUM(a.distance_mi) AS distance_mi
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d
    ON d.date_key = a.date_key
JOIN gold.dim_location l
    ON l.location_key = a.location_key
WHERE a.date_key BETWEEN $1 AND $2
  AND (
      $3 = 'all'
      OR d.is_weekend = ($3 = 'weekend')
  )
  AND (
      $4 IS NULL
      OR l.borough = $4
  )
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

EXPLAIN ANALYZE
EXECUTE stmt_kpi_monthly(20250101, 20251231, 'all', NULL);

-- 2b. SQL_KPI_DAILY
PREPARE stmt_kpi_daily (int, int, text, text) AS
SELECT 
    d.date_key, 
    SUM(a.trips) AS trips, 
    SUM(a.revenue) AS revenue
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d ON d.date_key = a.date_key
JOIN gold.dim_location l ON l.location_key = a.location_key
WHERE a.date_key BETWEEN $1 AND $2
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
  AND ($4 IS NULL OR l.borough = $4)
GROUP BY d.date_key 
ORDER BY d.date_key;

EXPLAIN ANALYZE
EXECUTE stmt_kpi_daily(20250101, 20251231, 'all', NULL);

-- Optimized ========================================================

DEALLOCATE stmt_kpi_daily;

PREPARE stmt_kpi_daily (int, int, text, text) AS
SELECT 
    a.date_key, 
    SUM(a.trips) AS trips, 
    SUM(a.revenue) AS revenue
FROM mart.agg_pickup_zone_day_band a
LEFT JOIN gold.dim_date d 
    ON d.date_key = a.date_key 
    AND $3 != 'all'
LEFT JOIN gold.dim_location l 
    ON l.location_key = a.location_key 
    AND $4 IS NOT NULL
WHERE a.date_key BETWEEN $1 AND $2
    AND ($3 = 'all' OR d.is_weekend = ($3 = 'weekend'))
    AND ($4 IS NULL OR l.borough = $4)
GROUP BY a.date_key 
ORDER BY a.date_key;

EXPLAIN ANALYZE
EXECUTE stmt_kpi_daily(20250101, 20251231, 'all', NULL);


-- 2c. SQL_KPI_Q1 Baseline
PREPARE stmt_kpi_q1 (int, int, text, text) AS
SELECT 
    SUM(a.revenue) AS revenue, 
    SUM(a.duration_min) AS duration_min, 
    SUM(a.distance_mi) AS distance_mi
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d ON d.date_key = a.date_key
JOIN gold.dim_location l ON l.location_key = a.location_key
WHERE a.date_key BETWEEN $1 AND $2
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
  AND ($4 IS NULL OR l.borough = $4);

-- Example call passing Q1 date key range
EXPLAIN ANALYZE
EXECUTE stmt_kpi_q1(20250101, 20250331, 'all', NULL);

-- Optimized
CREATE INDEX idx_dim_location_lookup 
ON gold.dim_location (location_key) 
INCLUDE (borough);

DEALLOCATE stmt_kpi_q1;

PREPARE stmt_kpi_q1 (int, int, text, text) AS
SELECT 
    SUM(a.revenue) AS revenue, 
    SUM(a.duration_min) AS duration_min, 
    SUM(a.distance_mi) AS distance_mi
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d ON d.date_key = a.date_key
JOIN gold.dim_location l ON l.location_key = a.location_key
WHERE a.date_key BETWEEN $1 AND $2
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
  AND ($4 IS NULL OR l.borough = $4);

-- Example call passing Q1 date key range
EXPLAIN ANALYZE
EXECUTE stmt_kpi_q1(20250101, 20250331, 'all', NULL);

-- 3. Where to Be: Zone & Borough Flow
-- Parameters:
-- $1 = start (YYYYMMDD integer, e.g. 20250101)
-- $2 = end   (YYYYMMDD integer, e.g. 20251231)
-- $3 = day_type ('all', 'weekday', or 'weekend')
-- $4 = borough (Borough name or NULL)
-- $5 = min_trips (Threshold integer, e.g. 2000)

-- 3a. SQL_ZONES (Pickup vs. Dropoff net flow at Zone level)
PREPARE stmt_zones (int, int, text, text, int) AS
WITH pu AS (
    SELECT 
        a.location_key, 
        SUM(a.trips) AS trips, 
        SUM(a.revenue) AS revenue, 
        SUM(a.duration_min) AS duration_min
    FROM mart.agg_pickup_zone_day_band a
    JOIN gold.dim_date d ON d.date_key = a.date_key
    WHERE a.date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
    GROUP BY a.location_key
), dof AS (
    SELECT 
        x.location_key, 
        SUM(x.trips) AS dropoffs
    FROM mart.agg_dropoff_zone_day x
    JOIN gold.dim_date d ON d.date_key = x.date_key
    WHERE x.date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
    GROUP BY x.location_key
)
SELECT 
    l.location_zone AS name, 
    l.borough, 
    pu.trips, 
    pu.revenue, 
    pu.duration_min,
    pu.revenue / (pu.duration_min / 60.0) AS rev_per_hour,
    100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / pu.trips AS net_flow_pct
FROM pu
JOIN gold.dim_location l ON l.location_key = pu.location_key
LEFT JOIN dof ON dof.location_key = pu.location_key
WHERE l.location_key <> -1 
  AND pu.trips >= $5 
  AND ($4 IS NULL OR l.borough = $4)
ORDER BY pu.trips DESC;

EXPLAIN ANALYZE
EXECUTE stmt_zones(20250101, 20251231, 'all', NULL, 2000);


-- 3b. SQL_BOROUGH_FLOW (Aggregated at Borough level)
PREPARE stmt_borough_flow (int, int, text, int) AS
WITH pu AS (
    SELECT 
        l.borough, 
        SUM(a.trips) AS trips, 
        SUM(a.revenue) AS revenue, 
        SUM(a.duration_min) AS duration_min
    FROM mart.agg_pickup_zone_day_band a
    JOIN gold.dim_date d ON d.date_key = a.date_key
    JOIN gold.dim_location l ON l.location_key = a.location_key
    WHERE a.date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend')) 
      AND l.location_key <> -1
    GROUP BY l.borough
), dof AS (
    SELECT 
        l.borough, 
        SUM(x.trips) AS dropoffs
    FROM mart.agg_dropoff_zone_day x
    JOIN gold.dim_date d ON d.date_key = x.date_key
    JOIN gold.dim_location l ON l.location_key = x.location_key
    WHERE x.date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend')) 
      AND l.location_key <> -1
    GROUP BY l.borough
)
SELECT 
    pu.borough AS name, 
    pu.borough, 
    pu.trips, 
    pu.revenue, 
    pu.duration_min,
    pu.revenue / (pu.duration_min / 60.0) AS rev_per_hour,
    100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / pu.trips AS net_flow_pct
FROM pu 
LEFT JOIN dof USING (borough)
WHERE pu.borough IS NOT NULL 
  AND pu.trips >= $4
ORDER BY pu.trips DESC;

EXPLAIN ANALYZE
EXECUTE stmt_borough_flow(20250101, 20251231, 'all', 2000);


-- 4. Corridors & Trip Length Distribution
-- 4a. SQL_CORRIDORS
-- Parameters:
-- $1 = start_month (YYYYMM integer, e.g. 202501)
-- $2 = end_month   (YYYYMM integer, e.g. 202512)
-- $3 = day_type    ('all', 'weekday', or 'weekend')
-- $4 = borough     (Borough name or NULL)
PREPARE stmt_corridors (int, int, text, text) AS
WITH days AS (
    SELECT COUNT(*) AS n 
    FROM gold.dim_date d
    WHERE d.date_key BETWEEN $1 * 100 + 1 AND $2 * 100 + 31 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
), pairs AS (
    SELECT 
        c.pickup_location_key AS pu_key, 
        c.dropoff_location_key AS do_key,
        SUM(c.trips) AS trips, 
        SUM(c.revenue) AS revenue, 
        SUM(c.duration_min) AS duration_min
    FROM mart.agg_corridor_month c
    WHERE c.month_key BETWEEN $1 AND $2
      AND ($3 = 'all' OR c.is_weekend = ($3 = 'weekend'))
    GROUP BY 1, 2
), top6 AS (
    SELECT p.* 
    FROM pairs p
    JOIN gold.dim_location l ON l.location_key = p.pu_key
    WHERE p.pu_key <> p.do_key 
      AND p.pu_key <> -1 
      AND p.do_key <> -1 
      AND ($4 IS NULL OR l.borough = $4)
    ORDER BY p.trips DESC 
    LIMIT 6
)
SELECT 
    lf.location_zone AS from_zone, 
    lt.location_zone AS to_zone,
    t.trips::float8 / days.n AS trips_per_day,
    t.revenue / (t.duration_min / 60.0) AS rev_per_hour,
    100.0 * COALESCE(r.trips, 0) / t.trips AS return_flow_pct
FROM top6 t
CROSS JOIN days
JOIN gold.dim_location lf ON lf.location_key = t.pu_key
JOIN gold.dim_location lt ON lt.location_key = t.do_key
LEFT JOIN pairs r ON r.pu_key = t.do_key AND r.do_key = t.pu_key
ORDER BY t.trips DESC;

EXPLAIN ANALYZE
EXECUTE stmt_corridors(202501, 202512, 'all', NULL);


-- 4b. SQL_TRIP_LENGTH
-- Parameters:
-- $1 = start (YYYYMMDD integer, e.g. 20250101)
-- $2 = end   (YYYYMMDD integer, e.g. 20251231)
-- $3 = day_type ('all', 'weekday', or 'weekend')
-- $4 = borough (Borough name or NULL)
PREPARE stmt_trip_length (int, int, text, text) AS
SELECT 
    a.length_band, 
    SUM(a.trips) AS trips,
    SUM(a.revenue) / (SUM(a.duration_min) / 60.0) AS rev_per_hour
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d ON d.date_key = a.date_key
JOIN gold.dim_location l ON l.location_key = a.location_key
WHERE a.date_key BETWEEN $1 AND $2 
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend')) 
  AND ($4 IS NULL OR l.borough = $4)
GROUP BY a.length_band 
ORDER BY a.length_band;

EXPLAIN ANALYZE
EXECUTE stmt_trip_length(20250101, 20251231, 'all', NULL);


-- 5. Slow Windows & Monthly Demand
-- Parameters:
-- $1 = start (YYYYMMDD integer, e.g. 20250101)
-- $2 = end   (YYYYMMDD integer, e.g. 20251231)
-- $3 = day_type ('all', 'weekday', or 'weekend')
-- $4 = borough (Borough name or NULL)

-- 5a. SQL_SLOW_HOUR (Speed vs Yield by hour)
PREPARE stmt_slow_hour (int, int, text, text) AS
SELECT 
    h.hour AS bucket, 
    SUM(h.trips) AS trips,
    SUM(h.revenue) / (SUM(h.duration_min) / 60.0) AS rev_per_hour,
    SUM(h.distance_mi) / (SUM(h.duration_min) / 60.0) AS avg_mph
FROM mart.agg_borough_day_hour h
JOIN gold.dim_date d ON d.date_key = h.date_key
WHERE h.date_key BETWEEN $1 AND $2
  AND ($4 IS NULL OR h.borough = $4) 
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
GROUP BY h.hour 
ORDER BY h.hour;

EXPLAIN ANALYZE
EXECUTE stmt_slow_hour(20250101, 20251231, 'all', NULL);


-- 5b. SQL_SLOW_PERIOD (Speed vs Yield by period using mart.hour_period view)
PREPARE stmt_slow_period (int, int, text, text) AS
SELECT 
    p.time_period AS bucket, 
    SUM(h.trips) AS trips,
    SUM(h.revenue) / (SUM(h.duration_min) / 60.0) AS rev_per_hour,
    SUM(h.distance_mi) / (SUM(h.duration_min) / 60.0) AS avg_mph
FROM mart.agg_borough_day_hour h
JOIN gold.dim_date d ON d.date_key = h.date_key
JOIN mart.hour_period p ON p.hour = h.hour
WHERE h.date_key BETWEEN $1 AND $2
  AND ($4 IS NULL OR h.borough = $4) 
  AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
GROUP BY p.time_period
ORDER BY array_position(ARRAY['Morning','Afternoon','Evening','Night','Late Night'], p.time_period);

EXPLAIN ANALYZE
EXECUTE stmt_slow_period(20250101, 20251231, 'all', NULL);


-- 5c. SQL_MONTHLY_DEMAND (Trips per calendar day)
PREPARE stmt_monthly_demand (int, int, text, text) AS
WITH m AS (
    SELECT 
        d.year, 
        d.month, 
        SUM(a.trips) AS trips
    FROM mart.agg_pickup_zone_day_band a
    JOIN gold.dim_date d ON d.date_key = a.date_key
    JOIN gold.dim_location l ON l.location_key = a.location_key
    WHERE a.date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend')) 
      AND ($4 IS NULL OR l.borough = $4)
    GROUP BY d.year, d.month
), n AS (
    SELECT 
        d.year, 
        d.month, 
        COUNT(*) AS n_days
    FROM gold.dim_date d
    WHERE d.date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR d.is_weekend::boolean = ($3 = 'weekend'))
    GROUP BY d.year, d.month
)
SELECT 
    m.year, 
    m.month, 
    m.trips, 
    n.n_days, 
    m.trips::float8 / n.n_days AS trips_per_day
FROM m 
JOIN n USING (year, month)
ORDER BY m.year, m.month;

EXPLAIN ANALYZE
EXECUTE stmt_monthly_demand(20250101, 20251231, 'all', NULL);