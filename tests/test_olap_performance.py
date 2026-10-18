"""
STADVDB MCO1 - Query Performance Benchmark Runner
Runs EXPLAIN ANALYZE on OLAP queries, measures planning and execution times,
and generates a performance comparison table for the technical report.
"""
import os
import re
import sys
import time
from pathlib import Path

# Add project root to sys.path so config.py and connections.py are importable regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import psycopg
except ImportError:
    import psycopg2 as psycopg
from config import WAREHOUSE_DB

def extract_execution_time(explain_output: list[str]) -> tuple[float, float]:
    """Extracts Planning Time and Execution Time (in ms) from EXPLAIN ANALYZE output."""
    plan_time, exec_time = 0.0, 0.0
    for line in explain_output:
        if "Planning Time:" in line:
            match = re.search(r"Planning Time:\s+([\d\.]+)\s+ms", line)
            if match:
                plan_time = float(match.group(1))
        elif "Execution Time:" in line:
            match = re.search(r"Execution Time:\s+([\d\.]+)\s+ms", line)
            if match:
                exec_time = float(match.group(1))
    return plan_time, exec_time

def run_benchmarks():
    print("=" * 70)
    print("STADVDB MCO1: OLAP Query Performance Testing")
    print(f"Connecting to {WAREHOUSE_DB['database']} at {WAREHOUSE_DB['host']}...")
    print("=" * 70)
    
    conn = psycopg.connect(
        host=WAREHOUSE_DB["host"],
        port=WAREHOUSE_DB["port"],
        dbname=WAREHOUSE_DB["database"],
        user=WAREHOUSE_DB["username"],
        password=WAREHOUSE_DB["password"]
    )
    conn.autocommit = True
    cur = conn.cursor()

    queries = [
        ("1a. SQL_BOROUGHS", """
            SELECT DISTINCT borough 
            FROM gold.dim_location
            WHERE location_key <> -1 
              AND borough IS NOT NULL 
            ORDER BY 1;
        """),
        ("1b. SQL_BOUNDS", """
            SELECT 
                MIN(date_key) AS lo, 
                MAX(date_key) AS hi 
            FROM mart.agg_pickup_zone_day_band;
        """),
        ("2a. SQL_KPI_MONTHLY", """
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
            WHERE a.date_key BETWEEN 20250101 AND 20251231
            GROUP BY d.year, d.month 
            ORDER BY d.year, d.month;
        """),
        ("2b. SQL_KPI_DAILY", """
            SELECT 
                d.date_key, 
                SUM(a.trips) AS trips, 
                SUM(a.revenue) AS revenue
            FROM mart.agg_pickup_zone_day_band a
            JOIN gold.dim_date d ON d.date_key = a.date_key
            JOIN gold.dim_location l ON l.location_key = a.location_key
            WHERE a.date_key BETWEEN 20250101 AND 20250131
            GROUP BY d.date_key 
            ORDER BY d.date_key;
        """),
        ("2c. SQL_KPI_Q1", """
            SELECT 
                SUM(a.revenue) AS revenue, 
                SUM(a.duration_min) AS duration_min, 
                SUM(a.distance_mi) AS distance_mi
            FROM mart.agg_pickup_zone_day_band a
            JOIN gold.dim_date d ON d.date_key = a.date_key
            JOIN gold.dim_location l ON l.location_key = a.location_key
            WHERE a.date_key BETWEEN 20250101 AND 20250331;
        """),
        ("3a. SQL_ZONES", """
            WITH filtered_dates AS (
                SELECT date_key FROM gold.dim_date
                WHERE date_key BETWEEN 20250101 AND 20251231 AND ('all' = 'all')
            ),
            target_zones AS (
                SELECT location_key, location_zone, borough
                FROM gold.dim_location WHERE location_key <> -1
            ),
            pu AS (
                SELECT a.location_key, SUM(a.trips) AS trips, SUM(a.revenue) AS revenue, SUM(a.duration_min) AS duration_min
                FROM mart.agg_pickup_zone_day_band a
                JOIN filtered_dates d ON d.date_key = a.date_key
                JOIN target_zones tz  ON tz.location_key = a.location_key
                GROUP BY a.location_key HAVING SUM(a.trips) >= 2000
            ),
            dof AS (
                SELECT x.location_key, SUM(x.trips) AS dropoffs
                FROM mart.agg_dropoff_zone_day x
                JOIN filtered_dates d ON d.date_key = x.date_key
                JOIN pu               ON pu.location_key = x.location_key
                GROUP BY x.location_key
            )
            SELECT tz.location_zone AS name, tz.borough, pu.trips, pu.revenue, pu.duration_min,
                   pu.revenue / NULLIF(pu.duration_min / 60.0, 0) AS rev_per_hour,
                   100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / NULLIF(pu.trips, 0) AS net_flow_pct
            FROM pu
            JOIN target_zones tz ON tz.location_key = pu.location_key
            LEFT JOIN dof        ON dof.location_key = pu.location_key
            ORDER BY pu.trips DESC;
        """),
        ("3b. SQL_BOROUGH_FLOW", """
            WITH filtered_dates AS (
                SELECT date_key FROM gold.dim_date
                WHERE date_key BETWEEN 20250101 AND 20251231 AND ('all' = 'all')
            ),
            pu AS (
                SELECT h.borough, SUM(h.trips) AS trips, SUM(h.revenue) AS revenue, SUM(h.duration_min) AS duration_min
                FROM mart.agg_borough_day_hour h
                JOIN filtered_dates d ON d.date_key = h.date_key
                WHERE h.borough <> 'Unknown'
                GROUP BY h.borough HAVING SUM(h.trips) >= 2000
            ),
            dof_zone AS (
                SELECT x.location_key, SUM(x.trips) AS dropoffs
                FROM mart.agg_dropoff_zone_day x
                JOIN filtered_dates d ON d.date_key = x.date_key
                GROUP BY x.location_key
            ),
            dof AS (
                SELECT l.borough, SUM(dz.dropoffs) AS dropoffs
                FROM dof_zone dz
                JOIN gold.dim_location l ON l.location_key = dz.location_key
                WHERE l.location_key <> -1
                GROUP BY l.borough
            )
            SELECT pu.borough AS name, pu.borough, pu.trips, pu.revenue, pu.duration_min,
                   pu.revenue / NULLIF(pu.duration_min / 60.0, 0) AS rev_per_hour,
                   100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / NULLIF(pu.trips, 0) AS net_flow_pct
            FROM pu LEFT JOIN dof USING (borough)
            ORDER BY pu.trips DESC;
        """),
        ("4a. SQL_CORRIDORS", """
            WITH days AS (
                SELECT COUNT(*) AS n FROM gold.dim_date d
                WHERE d.date_key BETWEEN 20250101 AND 20251231
            ),
            valid_pu_locations AS (
                SELECT location_key, location_zone, borough
                FROM gold.dim_location WHERE location_key <> -1
            ),
            top6 AS (
                SELECT c.pickup_location_key AS pu_key, c.dropoff_location_key AS do_key,
                       SUM(c.trips) AS trips, SUM(c.revenue) AS revenue, SUM(c.duration_min) AS duration_min
                FROM mart.agg_corridor_month c
                JOIN valid_pu_locations l ON l.location_key = c.pickup_location_key
                WHERE c.month_key BETWEEN 202501 AND 202512
                  AND c.dropoff_location_key <> -1 AND c.pickup_location_key <> c.dropoff_location_key
                GROUP BY c.pickup_location_key, c.dropoff_location_key
                ORDER BY trips DESC LIMIT 6
            ),
            reverse_flows AS (
                SELECT c.pickup_location_key AS pu_key, c.dropoff_location_key AS do_key, SUM(c.trips) AS return_trips
                FROM mart.agg_corridor_month c
                JOIN top6 t ON t.do_key = c.pickup_location_key AND t.pu_key = c.dropoff_location_key
                WHERE c.month_key BETWEEN 202501 AND 202512
                GROUP BY c.pickup_location_key, c.dropoff_location_key
            )
            SELECT lf.location_zone AS from_zone, lt.location_zone AS to_zone,
                   t.trips::float8 / NULLIF(days.n, 0) AS trips_per_day,
                   t.revenue / NULLIF(t.duration_min / 60.0, 0) AS rev_per_hour,
                   100.0 * COALESCE(rf.return_trips, 0) / NULLIF(t.trips, 0) AS return_flow_pct
            FROM top6 t
            CROSS JOIN days
            JOIN gold.dim_location lf ON lf.location_key = t.pu_key
            JOIN gold.dim_location lt ON lt.location_key = t.do_key
            LEFT JOIN reverse_flows rf ON rf.pu_key = t.do_key AND rf.do_key = t.pu_key
            ORDER BY t.trips DESC;
        """),
        ("4b. SQL_TRIP_LENGTH", """
            WITH filtered_dates AS (
                SELECT date_key FROM gold.dim_date WHERE date_key BETWEEN 20250101 AND 20251231
            ),
            filtered_locations AS (
                SELECT location_key FROM gold.dim_location WHERE location_key <> -1
            )
            SELECT a.length_band, SUM(a.trips) AS trips,
                   SUM(a.revenue) / NULLIF(SUM(a.duration_min) / 60.0, 0) AS rev_per_hour
            FROM mart.agg_pickup_zone_day_band a
            JOIN filtered_dates d     ON d.date_key = a.date_key
            JOIN filtered_locations l ON l.location_key = a.location_key
            GROUP BY a.length_band ORDER BY a.length_band;
        """),
        ("5a. SQL_SLOW_HOUR", """
            WITH filtered_dates AS (
                SELECT date_key FROM gold.dim_date WHERE date_key BETWEEN 20250101 AND 20251231
            )
            SELECT h.hour AS bucket, SUM(h.trips) AS trips,
                   SUM(h.revenue)     / NULLIF(SUM(h.duration_min) / 60.0, 0) AS rev_per_hour,
                   SUM(h.distance_mi) / NULLIF(SUM(h.duration_min) / 60.0, 0) AS avg_mph
            FROM mart.agg_borough_day_hour h
            JOIN filtered_dates d ON d.date_key = h.date_key
            GROUP BY h.hour ORDER BY h.hour;
        """),
        ("5b. SQL_SLOW_PERIOD", """
            WITH filtered_dates AS (
                SELECT date_key FROM gold.dim_date WHERE date_key BETWEEN 20250101 AND 20251231
            ),
            hourly_summary AS (
                SELECT h.hour, SUM(h.trips) AS trips, SUM(h.revenue) AS revenue,
                       SUM(h.duration_min) AS duration_min, SUM(h.distance_mi) AS distance_mi
                FROM mart.agg_borough_day_hour h
                JOIN filtered_dates d ON d.date_key = h.date_key
                GROUP BY h.hour
            )
            SELECT p.time_period AS bucket, SUM(hs.trips) AS trips,
                   SUM(hs.revenue)     / NULLIF(SUM(hs.duration_min) / 60.0, 0) AS rev_per_hour,
                   SUM(hs.distance_mi) / NULLIF(SUM(hs.duration_min) / 60.0, 0) AS avg_mph
            FROM hourly_summary hs
            JOIN mart.hour_period p ON p.hour = hs.hour
            GROUP BY p.time_period
            ORDER BY array_position(ARRAY['Morning','Afternoon','Evening','Night','Late Night'], p.time_period);
        """),
        ("5c. SQL_MONTHLY_DEMAND", """
            WITH date_filter AS (
                SELECT year, month, date_key, COUNT(*) OVER (PARTITION BY year, month) AS n_days
                FROM gold.dim_date WHERE date_key BETWEEN 20250101 AND 20251231
            ),
            monthly_calendar_days AS (
                SELECT DISTINCT year, month, n_days FROM date_filter
            ),
            monthly_trips AS (
                SELECT d.year, d.month, SUM(h.trips) AS trips
                FROM mart.agg_borough_day_hour h
                JOIN (SELECT DISTINCT year, month, date_key FROM date_filter) d ON d.date_key = h.date_key
                GROUP BY d.year, d.month
            )
            SELECT m.year, m.month, m.trips, c.n_days, m.trips::float8 / NULLIF(c.n_days, 0) AS trips_per_day
            FROM monthly_trips m 
            JOIN monthly_calendar_days c USING (year, month)
            ORDER BY m.year, m.month;
        """)
    ]

    print(f"\n{'Query Name':<25} | {'Cold Run (ms)':<15} | {'Warm Avg (ms)':<15} | {'Rows':<8}")
    print("-" * 70)

    for name, sql in queries:
        times = []
        row_count = 0
        for i in range(5):
            cur.execute(f"EXPLAIN ANALYZE {sql}")
            lines = [r[0] for r in cur.fetchall()]
            _, exec_ms = extract_execution_time(lines)
            times.append(exec_ms)
            if i == 0:
                cur.execute(sql)
                row_count = len(cur.fetchall())
        
        cold_time = times[0]
        warm_avg = sum(times[1:]) / len(times[1:])
        print(f"{name:<25} | {cold_time:<15.2f} | {warm_avg:<15.2f} | {row_count:<8}")

    cur.close()
    conn.close()
    print("=" * 70)
    print("Benchmark complete! You can copy the values above into Section 6.")

if __name__ == "__main__":
    try:
        run_benchmarks()
    except Exception as e:
        print(f"\n[ERROR] Unable to run benchmark: {e}")
        print("Please check your .env credentials using: python connections.py")
