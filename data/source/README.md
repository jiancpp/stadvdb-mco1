# STADVDB MCO1 - Source Database Pipeline

**Student Responsibility:** Data Acquisition & Source Database  
**Target Database:** `nyc_taxi_source`  
**Dataset:** NYC TLC Yellow Taxi Trip Records (2025, January – December)  
**Total Records:** 48,722,602 rows across 12 monthly Parquet files  

---

## Directory Structure

```text
data/
├── yellow_tripdata_2025-01.parquet ... 2025-12.parquet
└── source/
    ├── README.md                  # Complete technical setup and execution instructions
    ├── requirements.txt           # Python dependencies (psycopg, pyarrow, pandas, python-dotenv)
    ├── .env.example               # Template for PostgreSQL credentials
    ├── source_schema.sql          # Idempotent DDL for source table and manifest
    ├── test_connection.py         # Connectivity and database existence check
    ├── import_2025.py             # Memory-efficient batch importer with COPY & checkpointing
    ├── profile_source.py          # Empirical profiling of Parquet files and PostgreSQL records
    ├── validate_source.py         # 10-point validation suite (fidelity, nulls, row counts)
    ├── export_source.py           # pg_dump compressed backup and automated restore testing
    ├── reports/
    │   ├── dataset_profile.md     # Full statistical analysis of the 2025 dataset
    │   ├── monthly_row_counts.csv # Per-file row count reconciliation table
    │   └── validation_results.csv # PASS/FAIL validation test matrix
    └── docs/
        ├── restore_instructions.md# Restoration guide for team members
        ├── etl_handoff.md         # Schema and quality guide for warehouse ETL integration
        └── ai_usage_log.md        # Academic integrity and generative AI disclosure log
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (tested with Python 3.13)
- Running PostgreSQL 15+ instance (PostgreSQL 18 default on `localhost:5432`)
- Dependencies installed:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Configure Credentials
Copy `.env.example` to `.env` in this directory:
```bash
cp .env.example .env
```
Edit `.env` with your PostgreSQL password:
```ini
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=<your_password>
SOURCE_DB=nyc_taxi_source
```
*(Note: `.env` is ignored by Git and will never be committed.)*

---

## Pipeline Execution Workflow

### Step 1: Verify Connection & Create Source Database
```bash
python3 test_connection.py
```
This tests connectivity to PostgreSQL, checks server version, and automatically creates `nyc_taxi_source` if it does not already exist.

### Step 2: Test Import with a Small Sample
```bash
python3 import_2025.py --sample 10000
```
Streams 10,000 rows to verify type mapping, batching, and `COPY` execution.

### Step 3: Test a Single Full Month (January 2025)
```bash
python3 import_2025.py --month 1 --force
```
Imports all 3,475,226 rows of January 2025 and verifies row counts.

### Step 4: Import All 12 Months (Full 2025 Dataset)
```bash
python3 import_2025.py
```
Streams all 12 Parquet files (~48.7M rows) into PostgreSQL with batch progress bars, automatic checkpointing, and post-load index creation. Already completed files are safely skipped if the script is interrupted and resumed.

### Step 5: Profile the Dataset
```bash
python3 profile_source.py
```
Calculates actual statistics across all records (nulls, negative fares, zero distances, extreme values, out-of-year dates, and duplicate trip groups). Generates `reports/dataset_profile.md` and `reports/monthly_row_counts.csv`.

### Step 6: Execute Validation Test Suite
```bash
python3 validate_source.py
```
Runs 10 automated test suites verifying file existence, per-file row reconciliation, total counts, sample record fidelity, and null preservation. Saves results to `reports/validation_results.csv`.

### Step 7: Export Database Backup & Run Restore Test
```bash
python3 export_source.py --test-restore
```
Creates a compressed plain SQL dump (`dumps/nyc_taxi_source_<timestamp>.sql.gz`), generates step-by-step restore instructions in `docs/restore_instructions.md`, and runs an automated restore test in a temporary database.
