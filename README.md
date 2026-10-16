# STADVDB MCO1 — Query Processing in a Data Warehouse

Source database for NYC Yellow Taxi Trip Records (2025, January – December).

The source database is prepared, verified, and ready for ETL and Data Warehouse implementation.

---

## Source Database Details

- **Database:** `nyc_taxi_source`
- **Source Table:** `yellow_tripdata_2025`
- **Total Records:** `48,722,602` rows (all 12 monthly files imported)
- **Primary Key:** `trip_id`
- **Data Lineage:** `source_file` (e.g., `yellow_tripdata_2025-01.parquet`)

---

## How to Load the Database on Your Machine

### 1. Restore from SQL Dump (Recommended)

1. Get the dump file: `nyc_taxi_source_20261016_231753.sql.gz` (located in `data/source/dumps/`).
2. Run in terminal:
   ```bash
   createdb -h localhost -U postgres nyc_taxi_source
   gunzip -c data/source/dumps/nyc_taxi_source_20261016_231753.sql.gz | psql -h localhost -U postgres -d nyc_taxi_source
   ```
3. Verify record count:
   ```sql
   SELECT COUNT(*) FROM yellow_tripdata_2025;
   -- Expected: 48,722,602
   ```

### 2. Or Run the Importer Directly

```bash
cd data/source
cp .env.example .env
# Set PGPASSWORD in .env
pip install -r requirements.txt
python3 test_connection.py
python3 import_2025.py
```

---

## Connecting in Python (for ETL)

```python
import psycopg

conn = psycopg.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="<your_password>",
    dbname="nyc_taxi_source"
)
```

---

## Important Documentation

- **ETL Integration & Data Quality Notes:** [`data/source/docs/etl_handoff.md`](data/source/docs/etl_handoff.md)  
  *Contains column mappings, documented data anomalies (negative fares, null values, outliers), and reconciliation queries.*
- **Restore Instructions:** [`data/source/docs/restore_instructions.md`](data/source/docs/restore_instructions.md)
- **Dataset Profile & Statistics:** [`data/source/reports/dataset_profile.md`](data/source/reports/dataset_profile.md)
- **Validation Test Results (10/10 PASS):** [`data/source/reports/validation_results.csv`](data/source/reports/validation_results.csv)
- **Monthly Row Counts:** [`data/source/reports/monthly_row_counts.csv`](data/source/reports/monthly_row_counts.csv)
- **Pipeline Technical Details:** [`data/source/README.md`](data/source/README.md)
- **Academic AI Usage Log:** [`data/source/docs/ai_usage_log.md`](data/source/docs/ai_usage_log.md)
