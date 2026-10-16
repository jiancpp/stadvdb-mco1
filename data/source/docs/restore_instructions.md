# STADVDB MCO1 - Source Database Restoration Guide

This document provides clear, reproducible instructions for restoring the `nyc_taxi_source` PostgreSQL database on any group member's machine.

## Prerequisites
1. **PostgreSQL 15+** installed and running.
2. `psql` and `gunzip` (or standard terminal tools) available in PATH.
3. Access to the compressed SQL dump file: `nyc_taxi_source_20261016_231753.sql.gz`.

---

## Restoration Steps

### Method 1: Command Line (Fastest & Recommended)

1. Open your terminal and create the target database (if it doesn't already exist):
   ```bash
   createdb -h localhost -U postgres nyc_taxi_source
   ```

2. Navigate to the directory containing the dump file:
   ```bash
   cd data/source/dumps/
   ```

3. Decompress and stream the SQL dump directly into `nyc_taxi_source`:
   ```bash
   gunzip -c nyc_taxi_source_20261016_231753.sql.gz | psql -h localhost -U postgres -p 5432 -d nyc_taxi_source
   ```
   *(Enter your local PostgreSQL password when prompted.)*

> **Note:** The dump includes `--clean --if-exists`, which automatically drops existing tables and recreates schemas cleanly.

---

### Method 2: One-Liner (Automated Script)

You can also use the included restore test command:
```bash
python3 data/source/export_source.py --restore-only
```
This automatically restores the dump to a test database, reconciles all 48.7M row counts, and verifies schema integrity.

---

## Verifying Restoration

Run the following validation query to verify that all rows restored successfully:

```sql
-- Connect to nyc_taxi_source
\c nyc_taxi_source

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
