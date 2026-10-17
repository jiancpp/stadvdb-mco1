"""
NYC Yellow Taxi ETL Pipeline  -  nyc_taxi_source -> bronze -> silver -> gold

Usage (from project root):
    python -m etl.etl_pipeline                     # full run
    python -m etl.etl_pipeline --limit 1000000     # test with first 1M rows
    python -m etl.etl_pipeline bronze|silver|gold|reconcile

- Silver/Gold use transactional checkpoints and ON CONFLICT for resumability.
- On first use of checkpoints, existing rows are safely rechecked from the beginning.
- Each trip is accepted into Silver or rejected with one recorded reason.
- Official TLC Unknown codes are used for ratecode (99) and payment (5); 
  only vendor/location use -1 sentinels.
- TRUNCATE dependent data AND reset silver.etl_checkpoints for a full reload.
"""

import argparse
import sys
import time

from sqlalchemy import text

from config import IS_ETL_DEVELOPER
from connections import source_engine, warehouse_engine


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BATCH_SIZE = 500_000
# Configurable project-level validity thresholds (not official TLC limits).
MAX_DURATION_HOURS = 24
MAX_AVG_SPEED_MPH = 100
MAX_PASSENGERS = 6
MAX_DISTANCE_MILES = 500

ROW_LIMIT     = None  # set from --limit at runtime
LIMIT_TRIP_ID = None  # resolved trip_id ceiling for ROW_LIMIT; used by reconcile()

VALID_FROM       = "2025-01-01"
VALID_TO_PICKUP  = "2026-01-01"  # exclusive
VALID_TO_DROPOFF = "2026-01-02"  # exclusive
DIM_DATE_END     = "2026-01-01"  # inclusive

UNKNOWN_KEY = -1

# Source columns in order. trip_id is aliased to source_trip_id in bronze.
SRC_COLS = [
    "trip_id", "vendorid", "tpep_pickup_datetime", "tpep_dropoff_datetime",
    "passenger_count", "trip_distance", "ratecodeid", "store_and_fwd_flag",
    "pulocationid", "dolocationid", "payment_type", "fare_amount", "extra",
    "mta_tax", "tip_amount", "tolls_amount", "improvement_surcharge",
    "total_amount", "congestion_surcharge", "airport_fee",
    "cbd_congestion_fee", "source_file", "imported_at",
]
BRONZE_COLS = ["source_trip_id"] + SRC_COLS[1:]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def id_ranges(last_done, max_id, step=BATCH_SIZE):
    """Yield (lo, hi] ranges starting after last_done."""
    lo = last_done
    while lo < max_id:
        hi = min(lo + step, max_id)
        yield lo, hi
        lo = hi


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

def preflight():
    with source_engine.connect() as conn:
        bad = conn.execute(text("""
            SELECT filename, import_status, parquet_row_count, imported_row_count
            FROM import_manifest
            WHERE import_status <> 'COMPLETED'
               OR imported_row_count <> parquet_row_count
        """)).fetchall()
        expected = conn.execute(
            text("SELECT COALESCE(SUM(imported_row_count), 0) FROM import_manifest")
        ).scalar()
        actual = conn.execute(
            text("SELECT COUNT(*) FROM yellow_tripdata_2025")
        ).scalar()
    if bad:
        raise RuntimeError(f"Source import incomplete: {bad}")
    if expected != actual:
        raise RuntimeError(f"Manifest says {expected} rows but source table has {actual}")
    log(f"Preflight OK: {actual:,} source rows")


# ---------------------------------------------------------------------------
# Bronze
# ---------------------------------------------------------------------------

def load_bronze_ref_location():
    with source_engine.connect() as s:
        rows = s.execute(text(
            "SELECT locationid, borough, zone, service_zone FROM taxi_zone_lookup"
        )).mappings().all()
    with warehouse_engine.begin() as w:
        w.execute(text("TRUNCATE bronze.ref_location"))
        w.execute(
            text("""
                INSERT INTO bronze.ref_location (location_id, borough, zone, service_zone)
                VALUES (:locationid, :borough, :zone, :service_zone)
            """),
            [dict(r) for r in rows],
        )
    log(f"bronze.ref_location loaded: {len(rows)} rows")


def load_bronze_trips():
    src = source_engine.raw_connection()
    dwh = warehouse_engine.raw_connection()
    src_cols    = ", ".join(SRC_COLS)
    bronze_cols = ", ".join(BRONZE_COLS)
    try:
        with dwh.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(source_trip_id), 0) FROM bronze.yellow_taxi_trips")
            last_id = cur.fetchone()[0]

        with src.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MIN(trip_id), 0), COALESCE(MAX(trip_id), 0) "
                "FROM yellow_tripdata_2025"
            )
            min_src_id, max_id = cur.fetchone()
        src.rollback()

        if ROW_LIMIT:
            # Find the actual trip_id of the Nth row.
            with src.cursor() as cur:
                cur.execute(
                    "SELECT trip_id FROM yellow_tripdata_2025 "
                    "ORDER BY trip_id LIMIT 1 OFFSET %s",
                    (ROW_LIMIT - 1,),
                )
                row = cur.fetchone()
                limit_id = row[0] if row else max_id
            src.rollback()
            max_id = min(max_id, limit_id)
            log(f"Bronze: test mode - first {ROW_LIMIT:,} rows (trip_id <= {max_id:,})")
            global LIMIT_TRIP_ID
            LIMIT_TRIP_ID = max_id

        # Skip the gap between 0 and the first real trip_id on fresh loads.
        effective_lo = max(last_id, min_src_id - 1) if last_id == 0 else last_id

        log(f"Bronze: resuming after trip_id {effective_lo:,} (max {max_id:,})")
        for lo, hi in id_ranges(effective_lo, max_id):
            started = time.perf_counter()
            with src.cursor() as s, dwh.cursor() as d:
                with s.copy(
                    f"COPY (SELECT {src_cols} FROM yellow_tripdata_2025 "
                    f"WHERE trip_id > {lo} AND trip_id <= {hi}) TO STDOUT"
                ) as out, d.copy(
                    f"COPY bronze.yellow_taxi_trips ({bronze_cols}) FROM STDIN"
                ) as into:
                    for block in out:
                        into.write(block)
            dwh.commit()
            src.rollback()
            log(f"Bronze: trip_id <= {hi:,} / {max_id:,} ({time.perf_counter() - started:.1f}s)")
    finally:
        src.close()
        dwh.close()


def extract_load_bronze():
    load_bronze_ref_location()
    load_bronze_trips()


# ---------------------------------------------------------------------------
# Silver
# ---------------------------------------------------------------------------

DDL_REJECTED = """
CREATE TABLE IF NOT EXISTS silver.rejected_trips (
    source_trip_id  BIGINT PRIMARY KEY,
    reject_reason   VARCHAR(50) NOT NULL,
    source_file     VARCHAR(100),
    rejected_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
)
"""

# Accept/reject policy: Reject structurally invalid records, including trips
# exceeding configurable plausibility bounds. Negative monetary values are
# accepted because TLC data can include adjustments/refunds. Optional missing
# categorical codes map to documented Unknown values; missing fee components
# retain the existing 0-coalescing policy. The original data remains in Bronze.
# A record receives the first matching rejection reason below.
SILVER_BATCH_SQL = f"""
WITH checked AS (
    SELECT
        b.*,
        CASE
            WHEN b.tpep_pickup_datetime IS NULL
              OR b.tpep_dropoff_datetime IS NULL                  THEN 'missing_timestamp'
            WHEN b.tpep_pickup_datetime <  '{VALID_FROM}'
              OR b.tpep_pickup_datetime >= '{VALID_TO_PICKUP}'    THEN 'pickup_outside_2025'
            WHEN b.tpep_dropoff_datetime <= b.tpep_pickup_datetime THEN 'nonpositive_duration'
            WHEN b.tpep_dropoff_datetime >= '{VALID_TO_DROPOFF}'  THEN 'dropoff_out_of_range'
            WHEN b.tpep_dropoff_datetime - b.tpep_pickup_datetime
                 > INTERVAL '{MAX_DURATION_HOURS} hours'          THEN 'excessive_duration'
            WHEN b.trip_distance < 0                              THEN 'negative_distance'
            WHEN b.trip_distance > {MAX_DISTANCE_MILES}           THEN 'excessive_distance'
            WHEN b.trip_distance IS NOT NULL
                 AND EXTRACT(EPOCH FROM (b.tpep_dropoff_datetime - b.tpep_pickup_datetime)) > 0
                 AND b.trip_distance * 3600.0 /
                     EXTRACT(EPOCH FROM (b.tpep_dropoff_datetime - b.tpep_pickup_datetime))
                     > {MAX_AVG_SPEED_MPH}                         THEN 'excessive_speed'
            WHEN b.passenger_count < 0 OR b.passenger_count > {MAX_PASSENGERS}
                                                                    THEN 'invalid_passengers'
            WHEN b.fare_amount IS NULL OR b.total_amount IS NULL  THEN 'missing_primary_amount'
            WHEN b.trip_distance >= 99999999                       THEN 'distance_out_of_range'
            WHEN b.vendorid NOT BETWEEN -32768 AND 32767          THEN 'vendor_out_of_range'
            WHEN v.vendor_id IS NULL                              THEN 'unmapped_vendor'
            WHEN GREATEST(
                     ABS(b.fare_amount), ABS(b.extra), ABS(b.mta_tax),
                     ABS(b.tip_amount), ABS(b.tolls_amount),
                     ABS(b.improvement_surcharge), ABS(b.total_amount),
                     ABS(b.congestion_surcharge), ABS(b.airport_fee),
                     ABS(b.cbd_congestion_fee)) >= 99999999       THEN 'amount_out_of_range'
        END AS reject_reason,
        r.ratecode_id   AS ok_ratecode,
        pt.type_id      AS ok_payment,
        pl.location_id  AS ok_pickup,
        dl.location_id  AS ok_dropoff
    FROM bronze.yellow_taxi_trips b
    LEFT JOIN silver.ref_providers     v  ON v.vendor_id     = b.vendorid
    LEFT JOIN silver.ref_ratecode      r  ON r.ratecode_id   = b.ratecodeid
    LEFT JOIN silver.ref_payment_type  pt ON pt.type_id      = b.payment_type
    LEFT JOIN silver.ref_location      pl ON pl.location_id  = b.pulocationid
    LEFT JOIN silver.ref_location      dl ON dl.location_id  = b.dolocationid
    WHERE b.source_trip_id >  :lo
      AND b.source_trip_id <= :hi
),
rejected AS (
    INSERT INTO silver.rejected_trips (source_trip_id, reject_reason, source_file)
    SELECT source_trip_id, reject_reason, source_file
    FROM checked
    WHERE reject_reason IS NOT NULL
    ON CONFLICT (source_trip_id) DO NOTHING
)
INSERT INTO silver.yellow_taxi_trips (
    bronze_trip_id, vendor_id, pickup_datetime, dropoff_datetime,
    passenger_count, trip_distance, ratecode_id, store_and_fwd_flag,
    pickup_location_id, dropoff_location_id, payment_type,
    fare_amount, extra, mta_tax, tip_amount, tolls_amount,
    improvement_surcharge, total_amount, congestion_surcharge,
    airport_fee, cbd_congestion_fee, trip_duration_minutes
)
SELECT
    source_trip_id,
    vendorid::SMALLINT,
    tpep_pickup_datetime,
    tpep_dropoff_datetime,
    passenger_count::SMALLINT,
    ROUND(trip_distance::NUMERIC, 2),
    COALESCE(ok_ratecode, 99),
    CASE WHEN UPPER(TRIM(store_and_fwd_flag)) IN ('Y', 'N')
         THEN UPPER(TRIM(store_and_fwd_flag)) END,
    ok_pickup,
    ok_dropoff,
    COALESCE(ok_payment, 5),
    ROUND(fare_amount::NUMERIC, 2),
    ROUND(COALESCE(extra, 0)::NUMERIC, 2),
    ROUND(COALESCE(mta_tax, 0)::NUMERIC, 2),
    ROUND(COALESCE(tip_amount, 0)::NUMERIC, 2),
    ROUND(COALESCE(tolls_amount, 0)::NUMERIC, 2),
    ROUND(COALESCE(improvement_surcharge, 0)::NUMERIC, 2),
    ROUND(total_amount::NUMERIC, 2),
    ROUND(COALESCE(congestion_surcharge, 0)::NUMERIC, 2),
    ROUND(COALESCE(airport_fee, 0)::NUMERIC, 2),
    ROUND(COALESCE(cbd_congestion_fee, 0)::NUMERIC, 2),
    ROUND((EXTRACT(EPOCH FROM (tpep_dropoff_datetime - tpep_pickup_datetime))
           / 60.0)::NUMERIC, 2)
FROM checked
WHERE reject_reason IS NULL
ON CONFLICT (bronze_trip_id) DO NOTHING
"""


# Metadata table for transactional resumption.
DDL_CHECKPOINTS = """
CREATE TABLE IF NOT EXISTS silver.etl_checkpoints (
    stage TEXT PRIMARY KEY CHECK (stage IN ('silver', 'gold')),
    last_trip_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def ensure_etl_metadata(conn):
    conn.execute(text(DDL_CHECKPOINTS))


def last_checkpoint(conn, stage):
    # Absence of a checkpoint forces a safe initial re-scan, even when a
    # preexisting partial load contains a high trip_id.
    return conn.execute(text(
        "SELECT COALESCE((SELECT last_trip_id FROM silver.etl_checkpoints "
        "WHERE stage = :stage), 0)"
    ), {"stage": stage}).scalar()


def save_checkpoint(conn, stage, hi):
    conn.execute(text("""
        INSERT INTO silver.etl_checkpoints(stage, last_trip_id)
        VALUES (:stage, :hi)
        ON CONFLICT(stage) DO UPDATE
            SET last_trip_id = EXCLUDED.last_trip_id, updated_at = NOW()
    """), {"stage": stage, "hi": hi})


def load_silver_ref_location():
    # Upsert: silver.yellow_taxi_trips has a FK to this table.
    with warehouse_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO silver.ref_location (location_id, borough, location_zone, service_zone)
            SELECT location_id,
                   COALESCE(NULLIF(TRIM(borough), ''),      'Unknown'),
                   COALESCE(NULLIF(TRIM(zone), ''),         'Unknown'),
                   COALESCE(NULLIF(TRIM(service_zone), ''), 'Unknown')
            FROM bronze.ref_location
            ON CONFLICT (location_id) DO UPDATE SET
                borough       = EXCLUDED.borough,
                location_zone = EXCLUDED.location_zone,
                service_zone  = EXCLUDED.service_zone
        """))
    log("silver.ref_location loaded")


def check_silver_reference():
    for table in ("ref_providers", "ref_ratecode", "ref_payment_type"):
        n = scalar(warehouse_engine, f"SELECT COUNT(*) FROM silver.{table}")
        if n == 0:
            raise RuntimeError(
                f"silver.{table} is empty - run warehouse/sql/03_cleansed_tables.sql first"
            )
    for table, column, code in (
        ("ref_ratecode", "ratecode_id", 99),
        ("ref_payment_type", "type_id", 5),
    ):
        n = scalar(warehouse_engine,
                   f"SELECT COUNT(*) FROM silver.{table} WHERE {column} = {code}")
        if n != 1:
            raise RuntimeError(f"silver.{table} must contain official Unknown code {code}")


def transform_silver():
    check_silver_reference()
    load_silver_ref_location()
    with warehouse_engine.begin() as conn:
        conn.execute(text(DDL_REJECTED))
        ensure_etl_metadata(conn)

    with warehouse_engine.connect() as conn:
        last_id = last_checkpoint(conn, "silver")
        max_id = conn.execute(text(
            "SELECT COALESCE(MAX(source_trip_id), 0) FROM bronze.yellow_taxi_trips"
        )).scalar()

    log(f"Silver: resuming after trip_id {last_id:,} (max {max_id:,})")
    for lo, hi in id_ranges(last_id, max_id):
        started = time.perf_counter()
        with warehouse_engine.begin() as conn:
            conn.execute(text(SILVER_BATCH_SQL), {"lo": lo, "hi": hi})
            save_checkpoint(conn, "silver", hi)
        log(f"Silver: trip_id <= {hi:,} / {max_id:,} ({time.perf_counter() - started:.1f}s)")


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------

def load_dim_date(conn):
    conn.execute(text(f"""
        INSERT INTO gold.dim_date (
            date_key, full_date, day, day_name, day_of_week, week_of_year,
            month, month_name, quarter, year, is_weekend)
        SELECT TO_CHAR(d, 'YYYYMMDD')::INT,
               d,
               EXTRACT(DAY     FROM d)::SMALLINT,
               TO_CHAR(d, 'FMDay'),
               EXTRACT(ISODOW  FROM d)::SMALLINT,
               EXTRACT(WEEK    FROM d)::SMALLINT,
               EXTRACT(MONTH   FROM d)::SMALLINT,
               TO_CHAR(d, 'FMMonth'),
               EXTRACT(QUARTER FROM d)::SMALLINT,
               EXTRACT(YEAR    FROM d)::SMALLINT,
               EXTRACT(ISODOW  FROM d) IN (6, 7)
        FROM (SELECT g::DATE AS d
              FROM generate_series('{VALID_FROM}'::DATE,
                                   '{DIM_DATE_END}'::DATE,
                                   INTERVAL '1 day') g) days
        ON CONFLICT DO NOTHING
    """))


def load_dim_time(conn):
    conn.execute(text("""
        INSERT INTO gold.dim_time (
            time_key, full_time, hour, minute, second, am_pm, time_period)
        SELECT TO_CHAR(t, 'HH24MISS')::INT,
               t,
               EXTRACT(HOUR   FROM t)::SMALLINT,
               EXTRACT(MINUTE FROM t)::SMALLINT,
               EXTRACT(SECOND FROM t)::SMALLINT,
               CASE WHEN EXTRACT(HOUR FROM t) < 12 THEN 'AM' ELSE 'PM' END,
               CASE
                   WHEN EXTRACT(HOUR FROM t) <  5  THEN 'Late Night'
                   WHEN EXTRACT(HOUR FROM t) < 12  THEN 'Morning'
                   WHEN EXTRACT(HOUR FROM t) < 17  THEN 'Afternoon'
                   WHEN EXTRACT(HOUR FROM t) < 21  THEN 'Evening'
                   ELSE 'Night'
               END
        FROM (SELECT (TIME '00:00:00' + s * INTERVAL '1 second')::TIME AS t
              FROM generate_series(0, 86399) s) times
        ON CONFLICT DO NOTHING
    """))


# dim_* tables use GENERATED ALWAYS AS IDENTITY, so Unknown (-1) sentinels
# must be inserted with OVERRIDING SYSTEM VALUE.
def load_dim_vendor(conn):
    conn.execute(text(f"""
        INSERT INTO gold.dim_vendor (vendor_key, vendor_id, vendor_name)
        OVERRIDING SYSTEM VALUE
        VALUES ({UNKNOWN_KEY}, {UNKNOWN_KEY}, 'Unknown')
        ON CONFLICT DO NOTHING
    """))
    conn.execute(text("""
        INSERT INTO gold.dim_vendor (vendor_id, vendor_name)
        SELECT vendor_id, provider_name FROM silver.ref_providers
        ON CONFLICT (vendor_id) DO NOTHING
    """))


def load_dim_location(conn):
    conn.execute(text(f"""
        INSERT INTO gold.dim_location (location_key, location_id, borough, location_zone, service_zone)
        OVERRIDING SYSTEM VALUE
        VALUES ({UNKNOWN_KEY}, {UNKNOWN_KEY}, 'Unknown', 'Unknown', 'Unknown')
        ON CONFLICT DO NOTHING
    """))
    conn.execute(text("""
        INSERT INTO gold.dim_location (location_id, borough, location_zone, service_zone)
        SELECT location_id, borough, location_zone, service_zone
        FROM silver.ref_location
        ON CONFLICT (location_id) DO NOTHING
    """))


def load_dim_payment(conn):
    # TLC defines payment_type_id=5 as Unknown.
    conn.execute(text("""
        INSERT INTO gold.dim_payment (payment_type_id, payment_description)
        SELECT type_id, payment_type FROM silver.ref_payment_type
        ON CONFLICT (payment_type_id) DO NOTHING
    """))


def load_dim_ratecode(conn):
    # TLC defines ratecode_id=99 as Null/unknown.
    conn.execute(text("""
        INSERT INTO gold.dim_ratecode (ratecode_id, ratecode_name)
        SELECT ratecode_id, ratecode_name FROM silver.ref_ratecode
        ON CONFLICT (ratecode_id) DO NOTHING
    """))


def migrate_legacy_unknown_keys(conn):
    """Repoint old fact references to official TLC unknowns, then remove old sentinels.

    This handles a warehouse populated by an earlier version of the ETL.
    Existing sentinel rows are changed only if they are the old (-1, -1) rows.
    """
    for dimension, key_col, code_col, official_code in (
        ("payment", "payment_key", "payment_type_id", 5),
        ("ratecode", "ratecode_key", "ratecode_id", 99),
    ):
        dim = f"gold.dim_{dimension}"
        official_key = conn.execute(text(f"""
            SELECT {key_col} FROM {dim} WHERE {code_col} = :code
        """), {"code": official_code}).scalar()
        if official_key is None:
            raise RuntimeError(f"Missing TLC Unknown code {official_code} in {dim}")
        legacy_key = conn.execute(text(f"""
            SELECT {key_col} FROM {dim}
            WHERE {key_col} = -1 AND {code_col} = -1
        """)).scalar()
        if legacy_key is not None:
            changed = conn.execute(text(f"""
                UPDATE gold.fact_yellow_taxi_trips
                SET {key_col} = :official_key
                WHERE {key_col} = -1
            """), {"official_key": official_key}).rowcount
            conn.execute(text(f"""
                DELETE FROM {dim} WHERE {key_col} = -1 AND {code_col} = -1
            """))
            log(f"Replaced {changed:,} legacy -1 {dimension} fact keys with TLC code {official_code}")


def validate_gold_category_lookups(conn):
    """Fail rather than silently insert NULL category keys into Gold."""
    for label, sql in (
        ("payment", """
            SELECT COUNT(*) FROM silver.yellow_taxi_trips s
            LEFT JOIN gold.dim_payment d ON d.payment_type_id = s.payment_type
            WHERE d.payment_key IS NULL
        """),
        ("ratecode", """
            SELECT COUNT(*) FROM silver.yellow_taxi_trips s
            LEFT JOIN gold.dim_ratecode d ON d.ratecode_id = s.ratecode_id
            WHERE d.ratecode_key IS NULL
        """),
    ):
        missing = conn.execute(text(sql)).scalar()
        if missing:
            raise RuntimeError(f"Gold {label} lookup failed for {missing:,} Silver trips")


FACT_BATCH_SQL = """
INSERT INTO gold.fact_yellow_taxi_trips (
    bronze_trip_id,
    pickup_date_key, dropoff_date_key, pickup_time_key, dropoff_time_key,
    vendor_key, pickup_location_key, dropoff_location_key,
    payment_key, ratecode_key,
    passenger_count, trip_distance, trip_duration_minutes,
    fare_amount, extra, mta_tax, tip_amount, tolls_amount,
    improvement_surcharge, total_amount, congestion_surcharge,
    airport_fee, cbd_congestion_fee
)
SELECT
    s.bronze_trip_id,
    TO_CHAR(s.pickup_datetime,  'YYYYMMDD')::INT,
    TO_CHAR(s.dropoff_datetime, 'YYYYMMDD')::INT,
    TO_CHAR(s.pickup_datetime,  'HH24MISS')::INT,
    TO_CHAR(s.dropoff_datetime, 'HH24MISS')::INT,
    COALESCE(v.vendor_key,    -1),
    COALESCE(pl.location_key, -1),
    COALESCE(dl.location_key, -1),
    p.payment_key,
    r.ratecode_key,
    s.passenger_count,
    s.trip_distance,
    s.trip_duration_minutes,
    s.fare_amount, s.extra, s.mta_tax, s.tip_amount, s.tolls_amount,
    s.improvement_surcharge, s.total_amount, s.congestion_surcharge,
    s.airport_fee, s.cbd_congestion_fee
FROM silver.yellow_taxi_trips s
LEFT JOIN gold.dim_vendor   v  ON v.vendor_id       = s.vendor_id
LEFT JOIN gold.dim_location pl ON pl.location_id    = s.pickup_location_id
LEFT JOIN gold.dim_location dl ON dl.location_id    = s.dropoff_location_id
LEFT JOIN gold.dim_payment  p  ON p.payment_type_id = s.payment_type
LEFT JOIN gold.dim_ratecode r  ON r.ratecode_id     = s.ratecode_id
WHERE s.bronze_trip_id >  :lo
  AND s.bronze_trip_id <= :hi
ON CONFLICT (bronze_trip_id) DO NOTHING
"""


def load_gold():
    with warehouse_engine.begin() as conn:
        load_dim_date(conn)
        load_dim_time(conn)
        load_dim_vendor(conn)
        load_dim_location(conn)
        load_dim_payment(conn)
        load_dim_ratecode(conn)
        migrate_legacy_unknown_keys(conn)
        validate_gold_category_lookups(conn)
    log("Gold dimensions loaded; TLC Unknown codes verified")

    with warehouse_engine.begin() as conn:
        ensure_etl_metadata(conn)
    with warehouse_engine.connect() as conn:
        last_id = last_checkpoint(conn, "gold")
        max_id = conn.execute(text(
            "SELECT COALESCE(MAX(bronze_trip_id), 0) FROM silver.yellow_taxi_trips"
        )).scalar()

    log(f"Gold fact: resuming after trip_id {last_id:,} (max {max_id:,})")
    for lo, hi in id_ranges(last_id, max_id):
        started = time.perf_counter()
        with warehouse_engine.begin() as conn:
            conn.execute(text(FACT_BATCH_SQL), {"lo": lo, "hi": hi})
            save_checkpoint(conn, "gold", hi)
        log(f"Gold fact: trip_id <= {hi:,} / {max_id:,} ({time.perf_counter() - started:.1f}s)")


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def reconcile():
    where = f"WHERE trip_id <= {int(LIMIT_TRIP_ID)}" if LIMIT_TRIP_ID else ""
    src = scalar(source_engine, f"SELECT COUNT(*) FROM yellow_tripdata_2025 {where}")
    brz = scalar(warehouse_engine, "SELECT COUNT(*) FROM bronze.yellow_taxi_trips")
    slv = scalar(warehouse_engine, "SELECT COUNT(*) FROM silver.yellow_taxi_trips")
    rej = scalar(warehouse_engine, "SELECT COUNT(*) FROM silver.rejected_trips")
    fct = scalar(warehouse_engine, "SELECT COUNT(*) FROM gold.fact_yellow_taxi_trips")
    log(f"source={src:,} bronze={brz:,} silver={slv:,} rejected={rej:,} fact={fct:,}")

    problems = []
    if src != brz:
        problems.append("source != bronze")
    if brz != slv + rej:
        problems.append("bronze != silver + rejected")
    if slv != fct:
        problems.append("silver != fact")

    with warehouse_engine.connect() as conn:
        checks = {
            "accepted and rejected overlap": """
                SELECT COUNT(*) FROM silver.yellow_taxi_trips s
                JOIN silver.rejected_trips r ON r.source_trip_id = s.bronze_trip_id
            """,
            "bronze rows unclassified": """
                SELECT COUNT(*) FROM bronze.yellow_taxi_trips b
                LEFT JOIN silver.yellow_taxi_trips s ON s.bronze_trip_id = b.source_trip_id
                LEFT JOIN silver.rejected_trips r ON r.source_trip_id = b.source_trip_id
                WHERE s.bronze_trip_id IS NULL AND r.source_trip_id IS NULL
            """,
            "silver rows without gold fact": """
                SELECT COUNT(*) FROM silver.yellow_taxi_trips s
                LEFT JOIN gold.fact_yellow_taxi_trips f ON f.bronze_trip_id = s.bronze_trip_id
                WHERE f.bronze_trip_id IS NULL
            """,
        }
        checks["gold null payment/ratecode keys"] = """
            SELECT COUNT(*) FROM gold.fact_yellow_taxi_trips
            WHERE payment_key IS NULL OR ratecode_key IS NULL
        """
        for label, sql in checks.items():
            n = conn.execute(text(sql)).scalar()
            log(f"  {label}: {n:,}")
            if n:
                problems.append(f"{label}: {n}")

        # Check measures with an equality join rather than relying only on
        # total aggregates (which can mask swapped/missing values).
        mismatch = conn.execute(text("""
            SELECT COUNT(*) FROM silver.yellow_taxi_trips s
            JOIN gold.fact_yellow_taxi_trips f ON f.bronze_trip_id = s.bronze_trip_id
            WHERE s.total_amount IS DISTINCT FROM f.total_amount
               OR s.fare_amount IS DISTINCT FROM f.fare_amount
               OR s.trip_distance IS DISTINCT FROM f.trip_distance
               OR s.trip_duration_minutes IS DISTINCT FROM f.trip_duration_minutes
        """)).scalar()
        log(f"  silver/gold measure mismatches: {mismatch:,}")
        if mismatch:
            problems.append(f"measure mismatches: {mismatch}")

        measures = conn.execute(text("""
            SELECT 'silver' AS stage, COALESCE(SUM(total_amount),0) AS revenue,
                   COALESCE(SUM(trip_distance),0) AS distance
            FROM silver.yellow_taxi_trips
            UNION ALL
            SELECT 'gold', COALESCE(SUM(total_amount),0),
                   COALESCE(SUM(trip_distance),0)
            FROM gold.fact_yellow_taxi_trips
        """)).mappings().all()
        a, b = measures
        log(f"  silver totals: amount={a['revenue']} distance={a['distance']}")
        log(f"  gold totals:   amount={b['revenue']} distance={b['distance']}")
        if a['revenue'] != b['revenue'] or a['distance'] != b['distance']:
            problems.append("silver/gold aggregate measures differ")

        reasons = conn.execute(text("""
            SELECT reject_reason, COUNT(*) FROM silver.rejected_trips
            GROUP BY reject_reason ORDER BY COUNT(*) DESC
        """)).fetchall()
        for reason, n in reasons:
            log(f"  rejected [{reason}]: {n:,}")


    if problems:
        raise RuntimeError("Reconciliation failed: " + "; ".join(problems))
    log("Reconciliation passed")


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

STEPS = {
    "bronze":    extract_load_bronze,
    "silver":    transform_silver,
    "gold":      load_gold,
    "reconcile": reconcile,
}


def run_pipeline(steps=("bronze", "silver", "gold", "reconcile")):
    if str(IS_ETL_DEVELOPER).strip().lower() not in ("1", "true"):
        sys.exit("IS_ETL_DEVELOPER must be 1 to run the ETL (see .env).")
    if "bronze" in steps:
        preflight()
    for name in steps:
        started = time.perf_counter()
        log(f"=== {name.upper()} ===")
        STEPS[name]()
        log(f"=== {name.upper()} done in {time.perf_counter() - started:.1f}s ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NYC taxi ETL pipeline")
    parser.add_argument(
        "step", nargs="?", default="all",
        choices=["all", *STEPS.keys()],
        help="which step to run (default: all)",
    )
    parser.add_argument(
        "--limit", type=int,
        help="test mode: load only the first N source rows",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")
    ROW_LIMIT = args.limit
    run_pipeline(tuple(STEPS) if args.step == "all" else (args.step,))
