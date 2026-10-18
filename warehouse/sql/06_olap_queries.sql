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
-- Optimization Strategies Applied:
-- 1. Predicate Pushdown: Filter the date dimension by the requested date range and day type before joining it with the aggregated fact table.
-- 2. Pre-aggregation: Perform aggregation directly on the monthly KPI level using the existing mart.agg_pickup_zone_day_band table, avoiding unnecessary row-level fact processing.
-- 3. Conditional Filtering: Apply day-type and borough filters within their respective dimension CTEs to simplify the main aggregation query.
-- 4. Type Cast Elimination: Remove unnecessary boolean casting on is_weekend to reduce expression evaluation overhead.

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
-- Optimization Strategies Applied:
-- 1. Unnecessary Join Elimination: Use conditional LEFT JOIN operations to avoid matching dimension records when the corresponding filter is not needed.
-- 2. Join Predicate Pushdown: Move day-type and borough conditions into their respective join predicates, reducing unnecessary dimension lookups.
-- 3. Type Cast Elimination: Remove unnecessary boolean casting on is_weekend.
-- 4. Fact Table Grouping: Group directly by a.date_key, avoiding the need to retrieve the date key from the dimension table.

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
-- Optimization Strategies Applied:
-- 1. Composite Indexing: Introduce an index on gold.dim_location (location_key) to support location dimension lookups.
-- 2. Covering Index: Include borough in the index using INCLUDE (borough) to potentially satisfy borough attribute retrieval directly from the index.
-- 3. Index-Only Scan Potential: Allow PostgreSQL to retrieve the indexed location key and borough without necessarily accessing the underlying table heap.

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
  AND ($3 = 'all' OR d.is_weekend = ($3 = 'weekend'))
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
-- Optimization Strategies Applied:
--   1. Predicate Pushdown: Pre-filter gold.dim_date once in a CTE instead of joining inside multiple sub-blocks.
--   2. Zone Dimension Pruning: Filter target locations by borough early to prune non-matching zones.
--   3. Early Threshold Filtering: Apply `HAVING SUM(a.trips) >= $5` directly inside the pickup CTE.
--   4. Semi-Join Dropoffs: Only aggregate dropoffs for zones that qualified in the pickup step.
PREPARE stmt_zones (int, int, text, text, int) AS
WITH filtered_dates AS (
    SELECT date_key
    FROM gold.dim_date
    WHERE date_key BETWEEN $1 AND $2
      AND ($3 = 'all' OR is_weekend = ($3 = 'weekend'))
),
target_zones AS (
    SELECT location_key, location_zone, borough
    FROM gold.dim_location
    WHERE location_key <> -1
      AND ($4 IS NULL OR borough = $4)
),
pu AS (
    SELECT 
        a.location_key, 
        SUM(a.trips) AS trips, 
        SUM(a.revenue) AS revenue, 
        SUM(a.duration_min) AS duration_min
    FROM mart.agg_pickup_zone_day_band a
    JOIN filtered_dates d ON d.date_key = a.date_key
    JOIN target_zones tz  ON tz.location_key = a.location_key
    GROUP BY a.location_key
    HAVING SUM(a.trips) >= $5
),
dof AS (
    SELECT 
        x.location_key, 
        SUM(x.trips) AS dropoffs
    FROM mart.agg_dropoff_zone_day x
    JOIN filtered_dates d ON d.date_key = x.date_key
    JOIN pu               ON pu.location_key = x.location_key
    GROUP BY x.location_key
)
SELECT 
    tz.location_zone AS name, 
    tz.borough, 
    pu.trips, 
    pu.revenue, 
    pu.duration_min,
    pu.revenue / NULLIF(pu.duration_min / 60.0, 0) AS rev_per_hour,
    100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / NULLIF(pu.trips, 0) AS net_flow_pct
FROM pu
JOIN target_zones tz ON tz.location_key = pu.location_key
LEFT JOIN dof        ON dof.location_key = pu.location_key
ORDER BY pu.trips DESC;

EXPLAIN ANALYZE
EXECUTE stmt_zones(20250101, 20251231, 'all', NULL, 2000);


-- 3b. SQL_BOROUGH_FLOW (Aggregated at Borough level)
-- Optimization Strategies Applied:
--   1. Denormalization Advantage: Query mart.agg_borough_day_hour for pickups. It already contains
--      the denormalized 'borough' column, eliminating joins to gold.dim_location.
--   2. Early Aggregation (Aggregate-Then-Join): For dropoffs, aggregate mart.agg_dropoff_zone_day by
--      location_key first (shrinking to ~260 rows), then join dim_location to roll up to borough.
PREPARE stmt_borough_flow (int, int, text, int) AS
WITH filtered_dates AS (
    SELECT date_key
    FROM gold.dim_date
    WHERE date_key BETWEEN $1 AND $2
      AND ($3 = 'all' OR is_weekend = ($3 = 'weekend'))
),
pu AS (
    SELECT 
        h.borough, 
        SUM(h.trips) AS trips, 
        SUM(h.revenue) AS revenue, 
        SUM(h.duration_min) AS duration_min
    FROM mart.agg_borough_day_hour h
    JOIN filtered_dates d ON d.date_key = h.date_key
    WHERE h.borough <> 'Unknown'
    GROUP BY h.borough
    HAVING SUM(h.trips) >= $4
),
dof_zone AS (
    SELECT 
        x.location_key, 
        SUM(x.trips) AS dropoffs
    FROM mart.agg_dropoff_zone_day x
    JOIN filtered_dates d ON d.date_key = x.date_key
    GROUP BY x.location_key
),
dof AS (
    SELECT 
        l.borough, 
        SUM(dz.dropoffs) AS dropoffs
    FROM dof_zone dz
    JOIN gold.dim_location l ON l.location_key = dz.location_key
    WHERE l.location_key <> -1
    GROUP BY l.borough
)
SELECT 
    pu.borough AS name, 
    pu.borough, 
    pu.trips, 
    pu.revenue, 
    pu.duration_min,
    pu.revenue / NULLIF(pu.duration_min / 60.0, 0) AS rev_per_hour,
    100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / NULLIF(pu.trips, 0) AS net_flow_pct
FROM pu 
LEFT JOIN dof USING (borough)
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
-- Optimization Strategies Applied:
--   1. Early Pruning: Exclude intra-zone trips (pu_key = do_key) and invalid keys (-1) directly in WHERE.
--   2. Eliminate Full Self-Join: Avoid joining the entire aggregated pairs table back onto itself.
--      Instead, compute return trips solely for the top 6 OD corridors.
PREPARE stmt_corridors (int, int, text, text) AS
WITH days AS (
    SELECT COUNT(*) AS n 
    FROM gold.dim_date d
    WHERE d.date_key BETWEEN $1 * 100 + 1 AND $2 * 100 + 31 
      AND ($3 = 'all' OR d.is_weekend = ($3 = 'weekend'))
),
valid_pu_locations AS (
    SELECT location_key, location_zone, borough
    FROM gold.dim_location
    WHERE location_key <> -1
      AND ($4 IS NULL OR borough = $4)
),
top6 AS (
    SELECT 
        c.pickup_location_key  AS pu_key, 
        c.dropoff_location_key AS do_key,
        SUM(c.trips)           AS trips, 
        SUM(c.revenue)         AS revenue, 
        SUM(c.duration_min)    AS duration_min
    FROM mart.agg_corridor_month c
    JOIN valid_pu_locations l ON l.location_key = c.pickup_location_key
    WHERE c.month_key BETWEEN $1 AND $2
      AND ($3 = 'all' OR c.is_weekend = ($3 = 'weekend'))
      AND c.dropoff_location_key <> -1
      AND c.pickup_location_key <> c.dropoff_location_key
    GROUP BY c.pickup_location_key, c.dropoff_location_key
    ORDER BY trips DESC 
    LIMIT 6
),
reverse_flows AS (
    SELECT 
        c.pickup_location_key  AS pu_key,
        c.dropoff_location_key AS do_key,
        SUM(c.trips)           AS return_trips
    FROM mart.agg_corridor_month c
    JOIN top6 t ON t.do_key = c.pickup_location_key 
               AND t.pu_key = c.dropoff_location_key
    WHERE c.month_key BETWEEN $1 AND $2
      AND ($3 = 'all' OR c.is_weekend = ($3 = 'weekend'))
    GROUP BY c.pickup_location_key, c.dropoff_location_key
)
SELECT 
    lf.location_zone AS from_zone, 
    lt.location_zone AS to_zone,
    t.trips::float8 / NULLIF(days.n, 0) AS trips_per_day,
    t.revenue / NULLIF(t.duration_min / 60.0, 0) AS rev_per_hour,
    100.0 * COALESCE(rf.return_trips, 0) / NULLIF(t.trips, 0) AS return_flow_pct
FROM top6 t
CROSS JOIN days
JOIN gold.dim_location lf ON lf.location_key = t.pu_key
JOIN gold.dim_location lt ON lt.location_key = t.do_key
LEFT JOIN reverse_flows rf ON rf.pu_key = t.do_key AND rf.do_key = t.pu_key
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
-- Optimization Strategies Applied:
--   1. Two-Stage Aggregation (Early Aggregation): Compress hundreds of thousands of mart rows to 24 hourly rows FIRST.
--   2. Low-Cost Join: Join only the 24 hourly rows to mart.hour_period before grouping into the 5 periods.
PREPARE stmt_slow_period (int, int, text, text) AS
WITH filtered_dates AS (
    SELECT date_key 
    FROM gold.dim_date
    WHERE date_key BETWEEN $1 AND $2
      AND ($3 = 'all' OR is_weekend = ($3 = 'weekend'))
),
hourly_summary AS (
    SELECT 
        h.hour,
        SUM(h.trips)        AS trips,
        SUM(h.revenue)      AS revenue,
        SUM(h.duration_min) AS duration_min,
        SUM(h.distance_mi)  AS distance_mi
    FROM mart.agg_borough_day_hour h
    JOIN filtered_dates d ON d.date_key = h.date_key
    WHERE ($4 IS NULL OR h.borough = $4)
    GROUP BY h.hour
)
SELECT 
    p.time_period AS bucket, 
    SUM(hs.trips) AS trips,
    SUM(hs.revenue)     / NULLIF(SUM(hs.duration_min) / 60.0, 0) AS rev_per_hour,
    SUM(hs.distance_mi) / NULLIF(SUM(hs.duration_min) / 60.0, 0) AS avg_mph
FROM hourly_summary hs
JOIN mart.hour_period p ON p.hour = hs.hour
GROUP BY p.time_period
ORDER BY array_position(ARRAY['Morning','Afternoon','Evening','Night','Late Night'], p.time_period);

EXPLAIN ANALYZE
EXECUTE stmt_slow_period(20250101, 20251231, 'all', NULL);


-- 5c. SQL_MONTHLY_DEMAND (Trips per calendar day)
-- Optimization Strategies Applied:
--   1. Grain / Mart Optimization: Use mart.agg_borough_day_hour rather than agg_pickup_zone_day_band.
--      This avoids scanning zone-level length bands and eliminates the join to dim_location.
--   2. Pre-computed Calendar Days: Aggregate distinct days per year/month directly in the date CTE.
PREPARE stmt_monthly_demand (int, int, text, text) AS
WITH date_filter AS (
    SELECT 
        year, 
        month, 
        date_key,
        COUNT(*) OVER (PARTITION BY year, month) AS n_days
    FROM gold.dim_date
    WHERE date_key BETWEEN $1 AND $2 
      AND ($3 = 'all' OR is_weekend = ($3 = 'weekend'))
),
monthly_calendar_days AS (
    SELECT DISTINCT year, month, n_days
    FROM date_filter
),
monthly_trips AS (
    SELECT 
        d.year, 
        d.month, 
        SUM(h.trips) AS trips
    FROM mart.agg_borough_day_hour h
    JOIN (SELECT DISTINCT year, month, date_key FROM date_filter) d 
      ON d.date_key = h.date_key
    WHERE ($4 IS NULL OR h.borough = $4)
    GROUP BY d.year, d.month
)
SELECT 
    m.year, 
    m.month, 
    m.trips, 
    c.n_days, 
    m.trips::float8 / NULLIF(c.n_days, 0) AS trips_per_day
FROM monthly_trips m 
JOIN monthly_calendar_days c USING (year, month)
ORDER BY m.year, m.month;

EXPLAIN ANALYZE
EXECUTE stmt_monthly_demand(20250101, 20251231, 'all', NULL);