#!/usr/bin/env python3
"""
STADVDB MCO1 - Source Database Export & Restore Testing Script
Generates a complete, restorable PostgreSQL SQL dump using pg_dump.
Performs an automated restore test in a temporary database to verify backup integrity.

Outputs:
- data/source/dumps/nyc_taxi_source_<timestamp>.sql.gz
- data/source/docs/restore_instructions.md
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import psycopg

# Load environment configuration
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", None)
SOURCE_DB = os.getenv("SOURCE_DB", "nyc_taxi_source")
DEFAULT_DB = os.getenv("PGDATABASE", "postgres")

BASE_DIR = Path(__file__).resolve().parent
DUMPS_DIR = BASE_DIR / "dumps"
DOCS_DIR = BASE_DIR / "docs"
DUMPS_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

def find_postgres_binary(name):
    """Finds binary in standard PostgreSQL 18 path or PATH."""
    pg18_path = Path(f"/Library/PostgreSQL/18/bin/{name}")
    if pg18_path.exists():
        return str(pg18_path)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"Could not find PostgreSQL utility '{name}'.")

def export_database():
    """Dumps the source database schema and data into a compressed SQL dump."""
    pg_dump = find_postgres_binary("pg_dump")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_filename = f"nyc_taxi_source_{timestamp}.sql.gz"
    dump_path = DUMPS_DIR / dump_filename

    print(f"\n{'='*75}")
    print(f"Exporting database '{SOURCE_DB}' using pg_dump...")
    print(f"Target file: {dump_path}")
    print(f"{'='*75}\n")

    env = os.environ.copy()
    if PGPASSWORD:
        env["PGPASSWORD"] = PGPASSWORD

    cmd = [
        pg_dump,
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        "-d", SOURCE_DB,
        "--clean",
        "--if-exists",
        "--create",
        "--verbose"
    ]

    t0 = time.time()
    # Pipe pg_dump through gzip
    import gzip
    with open(dump_path, "wb") as f_out:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as proc:
            with gzip.open(f_out, "wb") as gz_out:
                shutil.copyfileobj(proc.stdout, gz_out)
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                print(f"[ERROR] pg_dump failed with code {proc.returncode}:\n{stderr.decode()}", file=sys.stderr)
                if dump_path.exists():
                    dump_path.unlink()
                return None

    duration = time.time() - t0
    filesize = dump_path.stat().st_size
    filesize_mb = filesize / (1024 * 1024)

    print(f"[SUCCESS] Export completed in {duration:.1f}s ({duration/60:.2f} mins).")
    print(f"File: {dump_path.name}")
    print(f"Size: {filesize_mb:.2f} MB ({filesize:,} bytes)")
    return dump_path

def run_restore_test(dump_path):
    """Restores the dump to a temporary database to verify restoration."""
    test_db = "nyc_taxi_source_restore_test"
    print(f"\n{'='*75}")
    print(f"Executing automated restore test in temporary database '{test_db}'...")
    print(f"{'='*75}\n")

    # Connect to default database to manage test_db
    with psycopg.connect(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=DEFAULT_DB, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{test_db}";')
            cur.execute(f'CREATE DATABASE "{test_db}";')
            print(f"Created temporary database '{test_db}'.")

    psql = find_postgres_binary("psql")
    env = os.environ.copy()
    if PGPASSWORD:
        env["PGPASSWORD"] = PGPASSWORD

    cmd = [
        psql,
        "-h", PGHOST,
        "-p", PGPORT,
        "-U", PGUSER,
        "-d", test_db,
        "-v", "ON_ERROR_STOP=1"
    ]

    import gzip
    t0 = time.time()
    with gzip.open(dump_path, "rb") as gz_in:
        proc = subprocess.run(cmd, input=gz_in.read(), capture_output=True, env=env)

    if proc.returncode != 0:
        print(f"[ERROR] Restore failed with code {proc.returncode}:\n{proc.stderr.decode()}", file=sys.stderr)
        return False

    restore_duration = time.time() - t0
    print(f"Restore executed in {restore_duration:.1f}s.")

    # Compare row counts
    with psycopg.connect(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=SOURCE_DB) as orig_conn, \
         psycopg.connect(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=test_db) as test_conn:
        with orig_conn.cursor() as c1, test_conn.cursor() as c2:
            c1.execute("SELECT COUNT(*) FROM yellow_tripdata_2025;")
            orig_cnt = c1.fetchone()[0]
            c2.execute("SELECT COUNT(*) FROM yellow_tripdata_2025;")
            test_cnt = c2.fetchone()[0]

            print(f"Original DB Rows: {orig_cnt:,}")
            print(f"Restored DB Rows: {test_cnt:,}")
            if orig_cnt == test_cnt:
                print(f"[SUCCESS] Restore verification PASSED! Row counts match 100%.")
            else:
                print(f"[ERROR] Row count mismatch: Original={orig_cnt}, Restored={test_cnt}", file=sys.stderr)

    # Clean up temporary database
    with psycopg.connect(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=DEFAULT_DB, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{test_db}";')
            print(f"Cleaned up temporary database '{test_db}'.")

    return True

def generate_restore_instructions(dump_filename="nyc_taxi_source_<timestamp>.sql.gz"):
    """Generates clear, step-by-step restoration instructions for groupmates."""
    doc_path = DOCS_DIR / "restore_instructions.md"
    content = f"""# STADVDB MCO1 - Source Database Restoration Guide

This document provides clear, reproducible instructions for restoring the `nyc_taxi_source` PostgreSQL database on any group member's machine.

## Prerequisites
1. **PostgreSQL 15+** installed and running.
2. `psql` and `gunzip` (or standard terminal tools) available in PATH.
3. Access to the compressed SQL dump file: `{dump_filename}`.

---

## Restoration Steps

### Method 1: Command Line (Fastest & Recommended)

1. Open your terminal and navigate to the directory containing the dump file:
   ```bash
   cd data/source/dumps/
   ```

2. Decompress and stream the SQL dump directly into PostgreSQL using `psql`:
   ```bash
   gunzip -c {dump_filename} | psql -h localhost -U postgres -p 5432 -d postgres
   ```
   *(Enter your local PostgreSQL password when prompted.)*

> **Note:** The dump includes `--clean --if-exists --create`, which automatically creates the `nyc_taxi_source` database and required schemas.

---

### Method 2: Manual Database Creation + psql Restore

1. Create the database:
   ```bash
   psql -h localhost -U postgres -c "CREATE DATABASE nyc_taxi_source;"
   ```

2. Restore the data:
   ```bash
   gunzip -c {dump_filename} | psql -h localhost -U postgres -d nyc_taxi_source
   ```

---

## Verifying Restoration

Run the following validation query to verify that all rows restored successfully:

```sql
-- Connect to nyc_taxi_source
\\c nyc_taxi_source

-- Check total record count (Expected: 48,722,602 rows)
SELECT COUNT(*) AS total_trips FROM yellow_tripdata_2025;

-- Check monthly breakdown
SELECT source_file, COUNT(*) AS row_count
FROM yellow_tripdata_2025
GROUP BY source_file
ORDER BY source_file;

-- Verify manifest status
SELECT filename, parquet_row_count, imported_row_count, import_status
FROM import_manifest
ORDER BY filename;
```

Expected Total Rows: **48,722,602**  
Expected Monthly Files: **12 files (January through December 2025)**
"""
    with open(doc_path, "w") as f:
        f.write(content)
    print(f"Saved: {doc_path}")

def main():
    dump_path = export_database()
    if dump_path:
        generate_restore_instructions(dump_path.name)
        if "--test-restore" in sys.argv:
            run_restore_test(dump_path)

if __name__ == "__main__":
    main()
