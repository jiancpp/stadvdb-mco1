"""
Opportunities & Efficiency dashboard API.

Every endpoint reads the small rollups in the `mart` schema (backend/sql/06_mart_views.sql),
never the 48M-row fact table. Results are cached in-process for CACHE_TTL seconds.

Env: DATABASE_URL=postgresql://user:password@host:5432/dbname
Metric definitions
  revenue per occupied hour = SUM(total_amount) / (SUM(trip_duration_minutes) / 60)
  revenue per mile          = SUM(total_amount) / SUM(trip_distance)
  net flow %                = (dropoffs - pickups) / pickups * 100   (negative = cabs leave quickly)
  return flow %             = trips B->A / trips A->B * 100
  avg speed                 = SUM(trip_distance) / (SUM(trip_duration_minutes) / 60)
"""
import json
import os
import time
from datetime import date
from typing import Literal, Optional

import psycopg2.extensions
from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

# numeric -> float so rows serialise to JSON directly
psycopg2.extensions.register_type(
    psycopg2.extensions.new_type(
        psycopg2.extensions.DECIMAL.values, "DEC2FLOAT", lambda v, _: float(v) if v is not None else None
    )
)

CACHE_TTL = 300
MIN_ZONE_TRIPS = 2000  # hide zones too small for a stable $/hr
_pool: Optional[ThreadedConnectionPool] = None
_cache: dict = {}


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 8, os.environ["DATABASE_URL"])
    return _pool


def run(sql: str, params: Optional[dict] = None) -> list[dict]:
    key = (sql, json.dumps(params, sort_keys=True, default=str))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    pool = _get_pool()
    conn = pool.getconn()
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        pool.putconn(conn)
    _cache[key] = (time.time(), rows)
    return rows


# ------------------------------------------------------------------ filters
DayType = Literal["all", "weekday", "weekend"]
MIN_DATE = date(2025, 1, 1)
MAX_DATE = date(2025, 12, 31)


def _key(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def filters(
    start: date = Query(MIN_DATE, ge=MIN_DATE, le=MAX_DATE),
    end: date = Query(MAX_DATE, ge=MIN_DATE, le=MAX_DATE),
    borough: Optional[str] = None,
    day_type: DayType = "all",
) -> dict:
    if borough in ("N/A", "Unknown"):
        borough = None
    return {
        "start": _key(start),
        "end": _key(end),
        "start_month": start.year * 100 + start.month,
        "end_month": end.year * 100 + end.month,
        "borough": borough or None,
        "day_type": day_type,
    }


# ------------------------------------------------------------------ SQL
# d = gold.dim_date, l = gold.dim_location, a = mart.agg_pickup_zone_day_band
DAY = "(%(day_type)s = 'all' OR d.is_weekend::boolean = (%(day_type)s = 'weekend'))"
BOROUGH = "(%(borough)s IS NULL OR l.borough = %(borough)s)"


def _agg(lo: str = "start", hi: str = "end") -> str:
    return f"""
FROM mart.agg_pickup_zone_day_band a
JOIN gold.dim_date d     ON d.date_key = a.date_key
JOIN gold.dim_location l ON l.location_key = a.location_key
WHERE a.date_key BETWEEN %({lo})s AND %({hi})s AND {DAY} AND {BOROUGH}"""


SQL_BOROUGHS = """
SELECT DISTINCT borough FROM gold.dim_location
WHERE location_key <> -1 AND borough IS NOT NULL AND borough NOT IN ('N/A', 'Unknown')
ORDER BY 1"""

SQL_BOUNDS = "SELECT MIN(date_key) AS lo, MAX(date_key) AS hi FROM mart.agg_pickup_zone_day_band"

# KPI cards: monthly rollup, daily rollup, and the Q1 baseline
SQL_KPI_MONTHLY = f"""
SELECT d.year, d.month, SUM(a.trips) AS trips, SUM(a.revenue) AS revenue,
       SUM(a.duration_min) AS duration_min, SUM(a.distance_mi) AS distance_mi
{_agg()}
GROUP BY d.year, d.month ORDER BY d.year, d.month"""

SQL_KPI_DAILY = f"""
SELECT d.date_key, SUM(a.trips) AS trips, SUM(a.revenue) AS revenue
{_agg()}
GROUP BY d.date_key ORDER BY d.date_key"""

SQL_KPI_Q1 = f"""
SELECT SUM(a.revenue) AS revenue, SUM(a.duration_min) AS duration_min, SUM(a.distance_mi) AS distance_mi
{_agg("q1_start", "q1_end")}"""

# Where to be: pay vs wait (zone level). Pickups and dropoffs are rolled up separately, then joined.
SQL_ZONES = f"""
WITH pu AS (
  SELECT a.location_key, SUM(a.trips) AS trips, SUM(a.revenue) AS revenue, SUM(a.duration_min) AS duration_min
  FROM mart.agg_pickup_zone_day_band a
  JOIN gold.dim_date d ON d.date_key = a.date_key
  WHERE a.date_key BETWEEN %(start)s AND %(end)s AND {DAY}
  GROUP BY a.location_key
), dof AS (
  SELECT x.location_key, SUM(x.trips) AS dropoffs
  FROM mart.agg_dropoff_zone_day x
  JOIN gold.dim_date d ON d.date_key = x.date_key
  WHERE x.date_key BETWEEN %(start)s AND %(end)s AND {DAY}
  GROUP BY x.location_key
)
SELECT l.location_zone AS name, l.borough, pu.trips, pu.revenue, pu.duration_min,
       pu.revenue / (pu.duration_min / 60.0)                          AS rev_per_hour,
       100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / pu.trips      AS net_flow_pct
FROM pu
JOIN gold.dim_location l ON l.location_key = pu.location_key
LEFT JOIN dof            ON dof.location_key = pu.location_key
WHERE l.location_key <> -1 AND pu.trips >= %(min_trips)s AND {BOROUGH}
ORDER BY pu.trips DESC"""

# Same thing rolled up to borough (ignores the borough filter, shows every borough)
SQL_BOROUGH_FLOW = f"""
WITH pu AS (
  SELECT l.borough, SUM(a.trips) AS trips, SUM(a.revenue) AS revenue, SUM(a.duration_min) AS duration_min
  FROM mart.agg_pickup_zone_day_band a
  JOIN gold.dim_date d     ON d.date_key = a.date_key
  JOIN gold.dim_location l ON l.location_key = a.location_key
  WHERE a.date_key BETWEEN %(start)s AND %(end)s AND {DAY} AND l.location_key <> -1
  GROUP BY l.borough
), dof AS (
  SELECT l.borough, SUM(x.trips) AS dropoffs
  FROM mart.agg_dropoff_zone_day x
  JOIN gold.dim_date d     ON d.date_key = x.date_key
  JOIN gold.dim_location l ON l.location_key = x.location_key
  WHERE x.date_key BETWEEN %(start)s AND %(end)s AND {DAY} AND l.location_key <> -1
  GROUP BY l.borough
)
SELECT pu.borough AS name, pu.borough, pu.trips, pu.revenue, pu.duration_min,
       pu.revenue / (pu.duration_min / 60.0)                          AS rev_per_hour,
       100.0 * (COALESCE(dof.dropoffs, 0) - pu.trips) / pu.trips      AS net_flow_pct
FROM pu LEFT JOIN dof USING (borough)
WHERE pu.borough IS NOT NULL AND pu.trips >= %(min_trips)s
ORDER BY pu.trips DESC"""

# Top corridors: busiest pickup->dropoff pairs, with the reverse pair for "return flow".
# Month grain: the range snaps to whole months. Intra-zone and unknown trips are excluded.
SQL_CORRIDORS = f"""
WITH days AS (
  SELECT COUNT(*) AS n FROM gold.dim_date d
  WHERE d.date_key BETWEEN %(start_month)s * 100 + 1 AND %(end_month)s * 100 + 31 AND {DAY}
), pairs AS (
  SELECT c.pickup_location_key AS pu_key, c.dropoff_location_key AS do_key,
         SUM(c.trips) AS trips, SUM(c.revenue) AS revenue, SUM(c.duration_min) AS duration_min
  FROM mart.agg_corridor_month c
  WHERE c.month_key BETWEEN %(start_month)s AND %(end_month)s
    AND (%(day_type)s = 'all' OR c.is_weekend = (%(day_type)s = 'weekend'))
  GROUP BY 1, 2
), top6 AS (
  SELECT p.* FROM pairs p
  JOIN gold.dim_location l ON l.location_key = p.pu_key
  WHERE p.pu_key <> p.do_key AND p.pu_key <> -1 AND p.do_key <> -1 AND {BOROUGH}
  ORDER BY p.trips DESC LIMIT 6
)
SELECT lf.location_zone AS from_zone, lt.location_zone AS to_zone,
       t.trips::float8 / days.n                                AS trips_per_day,
       t.revenue / (t.duration_min / 60.0)                     AS rev_per_hour,
       100.0 * COALESCE(r.trips, 0) / t.trips                  AS return_flow_pct
FROM top6 t
CROSS JOIN days
JOIN gold.dim_location lf ON lf.location_key = t.pu_key
JOIN gold.dim_location lt ON lt.location_key = t.do_key
LEFT JOIN pairs r ON r.pu_key = t.do_key AND r.do_key = t.pu_key
ORDER BY t.trips DESC"""

# Trip length sweet spot
SQL_TRIP_LENGTH = f"""
SELECT a.length_band, SUM(a.trips) AS trips,
       SUM(a.revenue) / (SUM(a.duration_min) / 60.0) AS rev_per_hour
{_agg()}
GROUP BY a.length_band ORDER BY a.length_band"""

# Slow windows: speed vs yield by pickup hour, or by time period
_SLOW_WHERE = f"""
WHERE h.date_key BETWEEN %(start)s AND %(end)s
  AND (%(borough)s IS NULL OR h.borough = %(borough)s) AND {DAY}"""

SQL_SLOW_HOUR = f"""
SELECT h.hour AS bucket, SUM(h.trips) AS trips,
       SUM(h.revenue)     / (SUM(h.duration_min) / 60.0) AS rev_per_hour,
       SUM(h.distance_mi) / (SUM(h.duration_min) / 60.0) AS avg_mph
FROM mart.agg_borough_day_hour h
JOIN gold.dim_date d ON d.date_key = h.date_key
{_SLOW_WHERE}
GROUP BY h.hour ORDER BY h.hour"""

SQL_SLOW_PERIOD = f"""
SELECT p.time_period AS bucket, SUM(h.trips) AS trips,
       SUM(h.revenue)     / (SUM(h.duration_min) / 60.0) AS rev_per_hour,
       SUM(h.distance_mi) / (SUM(h.duration_min) / 60.0) AS avg_mph
FROM mart.agg_borough_day_hour h
JOIN gold.dim_date d     ON d.date_key = h.date_key
JOIN mart.hour_period p  ON p.hour = h.hour
{_SLOW_WHERE}
GROUP BY p.time_period
ORDER BY array_position(ARRAY['Morning','Afternoon','Evening','Night','Late Night'], p.time_period)"""

# Monthly demand vs normal: trips per calendar day in each month
SQL_MONTHLY_DEMAND = f"""
WITH m AS (
  SELECT d.year, d.month, SUM(a.trips) AS trips
  {_agg()}
  GROUP BY d.year, d.month
), n AS (
  SELECT d.year, d.month, COUNT(*) AS n_days
  FROM gold.dim_date d
  WHERE d.date_key BETWEEN %(start)s AND %(end)s AND {DAY}
  GROUP BY d.year, d.month
)
SELECT m.year, m.month, m.trips, n.n_days, m.trips::float8 / n.n_days AS trips_per_day
FROM m JOIN n USING (year, month)
ORDER BY m.year, m.month"""

# ------------------------------------------------------------------ helpers
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
BANDS = ["Under 1 mi", "1 to 2 mi", "2 to 4 mi", "4 to 10 mi", "10+ mi"]


def _div(n, d):
    return n / d if n is not None and d else None


def _chg(cur, base):
    return (cur / base - 1) * 100 if cur is not None and base else None


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _last_delta(xs):
    return _chg(xs[-1], xs[-2]) if len(xs) > 1 else None


def _hour_label(h) -> str:
    h = int(h)
    return f"{h % 12 or 12}{'a' if h < 12 else 'p'}"


def _slow_window(pts: list[dict]):
    """Longest contiguous run of buckets whose speed is in the slowest 35% of the speed range."""
    if len(pts) < 3:
        return None
    speeds = [p["avg_mph"] for p in pts]
    thr = min(speeds) + 0.35 * (max(speeds) - min(speeds))
    best, cur = [], []
    for p in pts:
        cur = cur + [p] if p["avg_mph"] <= thr else []
        if len(cur) > len(best):
            best = cur
    if not best:
        return None
    return {
        "from": best[0]["label"],
        "to": best[-1]["label"],
        "avg_mph": _mean([p["avg_mph"] for p in best]),
        "rev_per_hour": _mean([p["rev_per_hour"] for p in best]),
    }


# ------------------------------------------------------------------ endpoints
@router.get("/filters")
def get_filters():
    b = run(SQL_BOROUGHS)
    return {
        "boroughs": [x["borough"] for x in b if x["borough"] not in ("N/A", "Unknown")],
        "min_date": "2025-01-01",
        "max_date": "2025-12-31",
    }


@router.get("/kpis")
def kpis(f: dict = Depends(filters)):
    monthly = run(SQL_KPI_MONTHLY, f)
    daily = run(SQL_KPI_DAILY, f)
    year = f["start"] // 10000
    q1 = (run(SQL_KPI_Q1, {**f, "q1_start": year * 10000 + 101, "q1_end": year * 10000 + 331}) or [{}])[0]

    def tot(k):
        return sum(r[k] or 0 for r in monthly)

    def rph(r):
        return _div(r["revenue"], (r["duration_min"] or 0) / 60)

    rev_hr = _div(tot("revenue"), tot("duration_min") / 60)
    rev_mi = _div(tot("revenue"), tot("distance_mi"))
    q1_hr = _div(q1.get("revenue"), (q1.get("duration_min") or 0) / 60)
    q1_mi = _div(q1.get("revenue"), q1.get("distance_mi"))

    def card(series):
        return {"value": _mean(series), "delta_pct": _last_delta(series), "series": series}

    return {
        "rev_per_hour": {"value": rev_hr, "delta_pct": _chg(rev_hr, q1_hr), "series": [rph(r) for r in monthly]},
        "rev_per_mile": {
            "value": rev_mi,
            "delta_pct": _chg(rev_mi, q1_mi),
            "series": [_div(r["revenue"], r["distance_mi"]) for r in monthly],
        },
        "avg_revenue": {"month": card([r["revenue"] for r in monthly]), "day": card([r["revenue"] for r in daily])},
        "avg_trips": {"month": card([r["trips"] for r in monthly]), "day": card([r["trips"] for r in daily])},
    }


@router.get("/zones")
def zones(level: Literal["zone", "borough"] = "zone", f: dict = Depends(filters)):
    rows = run(SQL_ZONES if level == "zone" else SQL_BOROUGH_FLOW, {**f, "min_trips": MIN_ZONE_TRIPS})
    hours = sum(r["duration_min"] for r in rows) / 60
    limit = 7 if level == "zone" else len(rows)
    return {
        "level": level,
        "avg_rev_per_hour": _div(sum(r["revenue"] for r in rows), hours),
        "points": [
            {
                "name": r["name"],
                "borough": r["borough"],
                "trips": r["trips"],
                "rev_per_hour": r["rev_per_hour"],
                "net_flow_pct": r["net_flow_pct"],
                "labeled": i < limit,
            }
            for i, r in enumerate(rows)
        ],
    }


@router.get("/corridors")
def corridors(f: dict = Depends(filters)):
    return [{"rank": i + 1, **r} for i, r in enumerate(run(SQL_CORRIDORS, f))]


@router.get("/trip-length")
def trip_length(f: dict = Depends(filters)):
    rows = run(SQL_TRIP_LENGTH, f)
    total = sum(r["trips"] for r in rows) or 1
    return [
        {"band": BANDS[int(r["length_band"]) - 1], "share_pct": 100 * r["trips"] / total, "rev_per_hour": r["rev_per_hour"]}
        for r in rows
    ]


@router.get("/slow-windows")
def slow_windows(mode: Literal["hour", "period"] = "hour", f: dict = Depends(filters)):
    rows = run(SQL_SLOW_HOUR if mode == "hour" else SQL_SLOW_PERIOD, f)
    pts = [
        {
            "label": _hour_label(r["bucket"]) if mode == "hour" else r["bucket"],
            "rev_per_hour": r["rev_per_hour"],
            "avg_mph": r["avg_mph"],
        }
        for r in rows
    ]
    yields = [p["rev_per_hour"] for p in pts]
    return {
        "points": pts,
        "slow_window": _slow_window(pts),
        "yield_ratio": _div(max(yields), min(yields)) if yields else None,
    }


@router.get("/monthly-demand")
def monthly_demand(f: dict = Depends(filters)):
    rows = run(SQL_MONTHLY_DEMAND, f)
    avg = _div(sum(r["trips"] for r in rows), sum(r["n_days"] for r in rows))
    return {
        "avg_trips_per_day": avg,
        "months": [
            {
                "month": MONTHS[int(r["month"]) - 1],
                "year": int(r["year"]),
                "trips_per_day": r["trips_per_day"],
                "pct_vs_avg": _chg(r["trips_per_day"], avg),
            }
            for r in rows
        ],
    }
