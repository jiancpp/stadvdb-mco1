# STADVDB MCO1 - Generative AI Usage & Disclosure Log

**Student Name:** Mariel Yasumuro  
**Assigned Responsibility:** Data Acquisition & Source Database  
**Course:** STADVDB (Advanced Database Systems) - MCO1  
**Dataset:** NYC TLC Yellow Taxi Trip Records (2025)  

---

## Academic Integrity Compliance

This log is maintained in strict compliance with the STADVDB Generative AI policy. Generative AI assistance was utilized exclusively for source database preparation, pipeline scripting, profiling, and validation under human supervision and independent empirical verification.

### Prohibited Scope Acknowledgement:
- [x] No dimensional warehouse schemas (star/snowflake) designed or modified.
- [x] No OLAP analytical queries or query optimizations generated.
- [x] No data profiling statistics fabricated; all statistics derived from actual execution on the 2025 dataset.
- [x] No validation or import claims made without empirical verification.

---

## Log of AI Assistance

### Entry 1: Repository & Parquet Inspection
- **Task:** Inspect repository structure, locate 12 monthly 2025 Parquet files, verify schemas, and examine existing PostgreSQL setup.
- **Assistance Provided:** Generated inspection routines to inspect Parquet metadata across all 12 monthly files (`yellow_tripdata_2025-01.parquet` through `yellow_tripdata_2025-12.parquet`), verifying row counts (48,722,602 total rows) and column uniformity. Checked IDE PostgreSQL extension configuration.
- **Independent Verification:** Ran Arrow inspection directly against all local files; verified presence of all 12 files and confirmed identical 20-column schema across each month.

### Entry 2: Source Database Schema Definition
- **Task:** Create PostgreSQL schema for `nyc_taxi_source` preserving raw dataset fidelity.
- **Assistance Provided:** Drafted `source_schema.sql` defining `yellow_tripdata_2025` with exact type mappings, case-insensitive column names, and audit lineage table `import_manifest`.
- **Independent Verification:** Verified data types against NYC TLC Yellow Taxi data dictionary; ensured all columns are nullable to preserve raw source anomalies, negatives, and nulls.

### Entry 3: Ingestion Pipeline Implementation
- **Task:** Build memory-efficient, resumable Python importer.
- **Assistance Provided:** Created `import_2025.py` utilizing `pyarrow` batch streaming and PostgreSQL `COPY FROM STDIN` via `psycopg 3` with checkpointing and per-file rollback capabilities.
- **Independent Verification:** Validated streaming throughput (100k rows in ~0.22s) and batch memory footprint (~15 MB).

### Entry 4: Profiling & Validation Framework
- **Task:** Build profiling and validation suites covering the 2025 dataset.
- **Assistance Provided:** Created `profile_source.py` and `validate_source.py` implementing 10 distinct validation tests (row counts, null counts, anomaly checks, idempotency, deterministic sample checks).
- **Independent Verification:** Executed tests against source files and verified outputs stored in `data/source/reports/`.

### Entry 5: Database Export & Restoration Documentation
- **Task:** Create export script and restoration guide for group members.
- **Assistance Provided:** Created `export_source.py` and `restore_instructions.md` with automated test restoration procedures.
- **Independent Verification:** Verified pg_dump syntax, gzipped streaming, and row-count comparison logic.
