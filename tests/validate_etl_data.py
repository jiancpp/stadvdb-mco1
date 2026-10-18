"""Read-only validation of a completed NYC taxi ETL load.

From project root (with configured DB access):
    python tests/validate_etl_data.py

Requires the project's connections.py to be importable. Does NOT run ETL,
truncate, insert, update, or delete anything. Checks the current whole tables;
do not use during an active or intentionally partial load.
"""

import sys
from pathlib import Path

# The project's config.py and connections.py live at project root in this ETL.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from connections import source_engine, warehouse_engine

failures = []


def check(label, sql, engine=warehouse_engine, params=None):
    with engine.connect() as connection:
        value = connection.execute(text(sql), params or {}).scalar()
    passed = value == 0
    print(f"{'PASS' if passed else 'FAIL'} | {label}: {value:,} problem row(s)")
    if not passed:
        failures.append((label, value))


def count(engine, relation):
    with engine.connect() as connection:
        return connection.execute(text(f'SELECT COUNT(*) FROM {relation}')).scalar()


def main():
    print('NYC Taxi ETL — live data validation (READ ONLY)\n')
    src = count(source_engine, 'yellow_tripdata_2025')
    brz = count(warehouse_engine, 'bronze.yellow_taxi_trips')
    slv = count(warehouse_engine, 'silver.yellow_taxi_trips')
    rej = count(warehouse_engine, 'silver.rejected_trips')
    fct = count(warehouse_engine, 'gold.fact_yellow_taxi_trips')
    print(f'Source={src:,} | Bronze={brz:,} | Silver={slv:,} | Rejected={rej:,} | Gold={fct:,}\n')
    for label, diff in [
        ('Source = Bronze', src - brz),
        ('Bronze = Silver + Rejected', brz - slv - rej),
        ('Silver = Gold facts', slv - fct),
    ]:
        passed = diff == 0
        print(f"{'PASS' if passed else 'FAIL'} | {label} (difference: {diff:,})")
        if not passed:
            failures.append((label, diff))

    # Count equality alone does not prove row identity or quality.
    check('Bronze rows not classified', '''
        SELECT COUNT(*) FROM bronze.yellow_taxi_trips b
        LEFT JOIN silver.yellow_taxi_trips s ON s.bronze_trip_id=b.source_trip_id
        LEFT JOIN silver.rejected_trips r ON r.source_trip_id=b.source_trip_id
        WHERE s.bronze_trip_id IS NULL AND r.source_trip_id IS NULL''')
    check('Silver/rejected overlap', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips s
        JOIN silver.rejected_trips r ON r.source_trip_id=s.bronze_trip_id''')
    check('Silver rows missing in Gold', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips s
        LEFT JOIN gold.fact_yellow_taxi_trips f ON f.bronze_trip_id=s.bronze_trip_id
        WHERE f.bronze_trip_id IS NULL''')
    check('Invalid rejected-trip reasons', '''
        SELECT COUNT(*) FROM silver.rejected_trips
        WHERE reject_reason NOT IN (
            'missing_timestamp','pickup_outside_2025','nonpositive_duration',
            'dropoff_out_of_range','excessive_duration','negative_distance',
            'excessive_distance','excessive_speed','invalid_passengers',
            'missing_primary_amount','distance_out_of_range','vendor_out_of_range',
            'unmapped_vendor','amount_out_of_range')''')
    check('Silver invalid pickup/dropoff timestamps', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips
        WHERE pickup_datetime IS NULL OR dropoff_datetime IS NULL
           OR pickup_datetime < TIMESTAMP '2025-01-01'
           OR pickup_datetime >= TIMESTAMP '2026-01-01'
           OR dropoff_datetime <= pickup_datetime
           OR dropoff_datetime >= TIMESTAMP '2026-01-02'
           OR dropoff_datetime - pickup_datetime > INTERVAL '24 hours' ''')
    check('Silver invalid distance, speed or passenger count', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips
        WHERE trip_distance < 0 OR trip_distance > 500
           OR trip_distance*3600.0 / NULLIF(EXTRACT(EPOCH FROM
                   (dropoff_datetime-pickup_datetime)),0) > 100
           OR passenger_count < 0 OR passenger_count > 6''')
    check('Silver missing primary amounts', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips
        WHERE fare_amount IS NULL OR total_amount IS NULL''')
    check('Silver missing official category codes', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips
        WHERE payment_type IS NULL OR ratecode_id IS NULL''')
    check('Gold missing or null dimension keys', '''
        SELECT COUNT(*) FROM gold.fact_yellow_taxi_trips f
        LEFT JOIN gold.dim_date pd ON pd.date_key=f.pickup_date_key
        LEFT JOIN gold.dim_date dd ON dd.date_key=f.dropoff_date_key
        LEFT JOIN gold.dim_time pt ON pt.time_key=f.pickup_time_key
        LEFT JOIN gold.dim_time dt ON dt.time_key=f.dropoff_time_key
        LEFT JOIN gold.dim_vendor v ON v.vendor_key=f.vendor_key
        LEFT JOIN gold.dim_location pl ON pl.location_key=f.pickup_location_key
        LEFT JOIN gold.dim_location dl ON dl.location_key=f.dropoff_location_key
        LEFT JOIN gold.dim_payment p ON p.payment_key=f.payment_key
        LEFT JOIN gold.dim_ratecode r ON r.ratecode_key=f.ratecode_key
        WHERE pd.date_key IS NULL OR dd.date_key IS NULL
           OR pt.time_key IS NULL OR dt.time_key IS NULL
           OR v.vendor_key IS NULL OR pl.location_key IS NULL
           OR dl.location_key IS NULL OR p.payment_key IS NULL
           OR r.ratecode_key IS NULL''')
    check('Silver/Gold mismatching measurements', '''
        SELECT COUNT(*) FROM silver.yellow_taxi_trips s
        JOIN gold.fact_yellow_taxi_trips f ON f.bronze_trip_id=s.bronze_trip_id
        WHERE s.fare_amount IS DISTINCT FROM f.fare_amount
           OR s.total_amount IS DISTINCT FROM f.total_amount
           OR s.trip_distance IS DISTINCT FROM f.trip_distance
           OR s.trip_duration_minutes IS DISTINCT FROM f.trip_duration_minutes''')
    check('Checkpoint behind processed Bronze/Silver IDs', '''
        SELECT COUNT(*) FROM (
            SELECT 'silver' AS stage,
                   (SELECT COALESCE(MAX(source_trip_id),0) FROM bronze.yellow_taxi_trips) AS required_id
            UNION ALL
            SELECT 'gold',
                   (SELECT COALESCE(MAX(bronze_trip_id),0) FROM silver.yellow_taxi_trips)
        ) required
        LEFT JOIN silver.etl_checkpoints c ON c.stage=required.stage
        WHERE (c.last_trip_id IS NULL OR c.last_trip_id < required.required_id)
          AND required.required_id > 0''')
    check('Missing payment Unknown code 5', '''
        SELECT CASE WHEN EXISTS (SELECT 1 FROM silver.ref_payment_type
                               WHERE type_id=5) THEN 0 ELSE 1 END''')
    check('Missing ratecode Unknown code 99', '''
        SELECT CASE WHEN EXISTS (SELECT 1 FROM silver.ref_ratecode
                               WHERE ratecode_id=99) THEN 0 ELSE 1 END''')

    print(f'\nResult: {"PASS" if not failures else "FAIL"} ({len(failures)} failing checks)')
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'VALIDATION ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(2) from exc
