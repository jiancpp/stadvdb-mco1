#!/usr/bin/env python3
"""
STADVDB MCO1 - 2025 NYC Yellow Taxi Data Importer
Imports all 12 months (Jan-Dec 2025) of Parquet data into PostgreSQL (nyc_taxi_source).

Key Features:
- Memory-efficient batch processing via PyArrow (RecordBatch streaming)
- High-performance bulk loading via PostgreSQL COPY FROM STDIN (binary/TSV)
- Checkpointing and resumable imports via import_manifest table
- Safe rollback handling per file
- Complete fidelity: preserves all original rows, nulls, negative values, and outliers
- Comprehensive logging and row-count verification
"""

import os
import sys
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import pyarrow as pa
import pyarrow.csv as pcsv
import pyarrow.parquet as pq
import psycopg

# Load environment configuration
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", None)
SOURCE_DB = os.getenv("SOURCE_DB", "nyc_taxi_source")
DEFAULT_DB = os.getenv("PGDATABASE", "postgres")
BATCH_SIZE = int(os.getenv("IMPORT_BATCH_SIZE", "100000"))

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data"

EXPECTED_FILES = [f"yellow_tripdata_2025-{m:02d}.parquet" for m in range(1, 13)]

COLUMN_NAMES = [
    "vendorid",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "ratecodeid",
    "store_and_fwd_flag",
    "pulocationid",
    "dolocationid",
    "payment_type",
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "total_amount",
    "congestion_surcharge",
    "airport_fee",
    "cbd_congestion_fee",
    "source_file"
]

def get_connection(dbname=SOURCE_DB, autocommit=False):
    """Establishes a connection to the specified PostgreSQL database."""
    return psycopg.connect(
        host=PGHOST,
        port=PGPORT,
        user=PGUSER,
        password=PGPASSWORD,
        dbname=dbname,
        autocommit=autocommit
    )

def ensure_database_and_schema():
    """Ensures that the nyc_taxi_source database and schema tables exist."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking target database '{SOURCE_DB}'...")
    # Step 1: Check database existence
    with get_connection(dbname=DEFAULT_DB, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (SOURCE_DB,))
            if not cur.fetchone():
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating database '{SOURCE_DB}'...")
                cur.execute(f'CREATE DATABASE "{SOURCE_DB}";')
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Database '{SOURCE_DB}' exists.")

    # Step 2: Apply schema definition from source_schema.sql
    schema_file = BASE_DIR / "source_schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found at {schema_file}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Applying schema from {schema_file.name}...")
    with get_connection(dbname=SOURCE_DB, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_file.read_text())
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Schema verified successfully.")

def calculate_md5(filepath, chunk_size=8192 * 1024):
    """Calculates MD5 checksum of a file efficiently."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()

def check_file_status(cur, filename):
    """Checks import manifest for file status and row counts."""
    cur.execute(
        "SELECT parquet_row_count, imported_row_count, import_status FROM import_manifest WHERE filename = %s;",
        (filename,)
    )
    return cur.fetchone()

def import_parquet_file(filepath, sample_limit=None, force=False):
    """Imports a single Parquet file into yellow_tripdata_2025."""
    filename = filepath.name
    filesize = filepath.stat().st_size
    pf = pq.ParquetFile(filepath)
    total_parquet_rows = pf.metadata.num_rows

    target_rows = sample_limit if sample_limit and sample_limit < total_parquet_rows else total_parquet_rows
    print(f"\n{'='*70}")
    print(f"Processing: {filename}")
    print(f"File Size: {filesize:,} bytes | Parquet Rows: {total_parquet_rows:,} (Target: {target_rows:,})")
    print(f"{'='*70}")

    with get_connection(dbname=SOURCE_DB) as conn:
        with conn.cursor() as cur:
            # Check manifest
            status = check_file_status(cur, filename)
            if status and not force and sample_limit is None:
                p_rows, i_rows, imp_status = status
                if imp_status == "COMPLETED" and i_rows == total_parquet_rows:
                    print(f"[SKIP] {filename} is already fully imported ({i_rows:,} rows). Use --force to reload.")
                    return True

            # If re-importing or previous incomplete attempt, delete existing rows for this file
            if status:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Cleaning up previous rows for {filename}...")
                cur.execute("DELETE FROM yellow_tripdata_2025 WHERE source_file = %s;", (filename,))
                conn.commit()

            # Record / update manifest to IN_PROGRESS
            cur.execute("""
                INSERT INTO import_manifest (filename, file_size_bytes, parquet_row_count, import_status, started_at)
                VALUES (%s, %s, %s, 'IN_PROGRESS', CURRENT_TIMESTAMP)
                ON CONFLICT (filename) DO UPDATE SET
                    file_size_bytes = EXCLUDED.file_size_bytes,
                    parquet_row_count = EXCLUDED.parquet_row_count,
                    import_status = 'IN_PROGRESS',
                    started_at = CURRENT_TIMESTAMP,
                    completed_at = NULL,
                    error_message = NULL;
            """, (filename, filesize, total_parquet_rows))
            conn.commit()

        # Stream batches into PostgreSQL using COPY FROM STDIN
        start_time = time.time()
        imported_rows = 0
        batch_num = 0

        copy_sql = f"""
            COPY yellow_tripdata_2025 ({', '.join(COLUMN_NAMES)})
            FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', QUOTE '"', ESCAPE '"', NULL E'\\\\N')
        """

        try:
            with conn.cursor() as cur:
                with cur.copy(copy_sql) as copy_op:
                    for batch in pf.iter_batches(batch_size=BATCH_SIZE):
                        batch_len = len(batch)
                        if sample_limit and (imported_rows + batch_len) > sample_limit:
                            slice_len = sample_limit - imported_rows
                            batch = batch.slice(0, slice_len)
                            batch_len = slice_len

                        batch_table = pa.Table.from_batches([batch])
                        # Append source_file column
                        file_col = pa.array([filename] * batch_len, pa.string())
                        batch_table = batch_table.append_column("source_file", file_col)

                        # Write to in-memory TSV buffer
                        import io
                        tsv_buf = io.BytesIO()
                        pcsv.write_csv(
                            batch_table,
                            tsv_buf,
                            write_options=pcsv.WriteOptions(
                                include_header=False,
                                delimiter='\t',
                                null_string=r'\N'
                            )
                        )
                        copy_op.write(tsv_buf.getvalue())
                        imported_rows += batch_len
                        batch_num += 1

                        elapsed = time.time() - start_time
                        rate = imported_rows / elapsed if elapsed > 0 else 0
                        print(
                            f"\r  Batch {batch_num:>3}: {imported_rows:>9,} / {target_rows:,} rows "
                            f"({(imported_rows / target_rows) * 100:>5.1f}%) | "
                            f"{rate:>7.0f} rows/s | {elapsed:>5.1f}s",
                            end="",
                            flush=True
                        )

                        if sample_limit and imported_rows >= sample_limit:
                            break

            print()  # newline after progress bar
            conn.commit()
            duration = time.time() - start_time
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COPY complete in {duration:.2f}s ({imported_rows / duration:.0f} rows/s).")

            # Verify count in database
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM yellow_tripdata_2025 WHERE source_file = %s;", (filename,))
                db_count = cur.fetchone()[0]

                if sample_limit is None and db_count != total_parquet_rows:
                    error_msg = f"Count mismatch for {filename}: Parquet={total_parquet_rows:,}, DB={db_count:,}"
                    print(f"[ERROR] {error_msg}", file=sys.stderr)
                    cur.execute("""
                        UPDATE import_manifest SET
                            imported_row_count = %s,
                            import_status = 'FAILED',
                            completed_at = CURRENT_TIMESTAMP,
                            execution_time_seconds = %s,
                            error_message = %s
                        WHERE filename = %s;
                    """, (db_count, duration, error_msg, filename))
                    conn.commit()
                    return False

                # Mark COMPLETED
                cur.execute("""
                    UPDATE import_manifest SET
                        imported_row_count = %s,
                        import_status = 'COMPLETED',
                        completed_at = CURRENT_TIMESTAMP,
                        execution_time_seconds = %s,
                        error_message = NULL
                    WHERE filename = %s;
                """, (db_count, duration, filename))
                conn.commit()

            print(f"[SUCCESS] {filename} imported successfully ({db_count:,} rows verified).")
            return True

        except Exception as e:
            conn.rollback()
            duration = time.time() - start_time
            print(f"\n[ERROR] Failed to import {filename}: {e}", file=sys.stderr)
            with get_connection(dbname=SOURCE_DB) as err_conn:
                with err_conn.cursor() as cur:
                    cur.execute("""
                        UPDATE import_manifest SET
                            import_status = 'FAILED',
                            completed_at = CURRENT_TIMESTAMP,
                            execution_time_seconds = %s,
                            error_message = %s
                        WHERE filename = %s;
                    """, (duration, str(e), filename))
                    err_conn.commit()
            return False

def ensure_indexes():
    """Creates indexes if they do not exist after bulk loading."""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Verifying / creating indexes...")
    with get_connection(dbname=SOURCE_DB, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_yellow_tripdata_source_file 
                    ON yellow_tripdata_2025 (source_file);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_yellow_tripdata_pickup 
                    ON yellow_tripdata_2025 (tpep_pickup_datetime);
            """)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Indexes ready.")

def main():
    parser = argparse.ArgumentParser(description="STADVDB MCO1 - 2025 NYC Yellow Taxi Data Importer")
    parser.add_argument("--sample", type=int, default=None, help="Import only N sample rows (e.g. 10000) for testing")
    parser.add_argument("--month", type=int, default=None, choices=range(1, 13), help="Import only a specific month (1-12)")
    parser.add_argument("--force", action="store_true", help="Force re-import of files even if already completed")
    parser.add_argument("--status-only", action="store_true", help="Display current import status from import_manifest")
    args = parser.parse_args()

    # Step 1: Ensure database & schema
    ensure_database_and_schema()

    # If status only
    if args.status_only:
        with get_connection(dbname=SOURCE_DB) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT filename, file_size_bytes, parquet_row_count, imported_row_count,
                           import_status, execution_time_seconds, completed_at
                    FROM import_manifest ORDER BY filename;
                """)
                rows = cur.fetchall()
                print("\nCURRENT IMPORT MANIFEST:")
                print(f"{'Filename':<35} {'Size (MB)':>10} {'Parquet Rows':>14} {'Imported Rows':>14} {'Status':>12} {'Secs':>8}")
                print("-" * 100)
                tot_p = tot_i = 0
                for r in rows:
                    size_mb = r[1] / (1024 * 1024)
                    tot_p += r[2]
                    tot_i += r[3]
                    print(f"{r[0]:<35} {size_mb:>10.2f} {r[2]:>14,} {r[3]:>14,} {r[4]:>12} {r[5] or 0:>8.1f}")
                print("-" * 100)
                print(f"{'TOTAL':<35} {'':>10} {tot_p:>14,} {tot_i:>14,}")
        return

    # Determine files to process
    if args.month:
        target_files = [f"yellow_tripdata_2025-{args.month:02d}.parquet"]
    else:
        target_files = EXPECTED_FILES

    # Verify files exist in DATA_DIR
    missing = [f for f in target_files if not (DATA_DIR / f).exists()]
    if missing:
        print(f"[FATAL] Missing required Parquet files in {DATA_DIR}: {missing}", file=sys.stderr)
        sys.exit(1)

    overall_start = time.time()
    success_count = 0

    print(f"\nStarting import process for {len(target_files)} file(s)...")
    for f in target_files:
        filepath = DATA_DIR / f
        ok = import_parquet_file(filepath, sample_limit=args.sample, force=args.force)
        if ok:
            success_count += 1
        else:
            print(f"[WARNING] Import stopped due to error on {f}.", file=sys.stderr)
            break

    # Build indexes if doing full import
    if args.sample is None and success_count == len(target_files):
        ensure_indexes()

    overall_duration = time.time() - overall_start
    print(f"\n{'='*70}")
    print(f"Import Run Summary:")
    print(f"Files Processed: {success_count} / {len(target_files)}")
    print(f"Total Execution Time: {overall_duration:.2f}s ({overall_duration/60:.2f} mins)")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
