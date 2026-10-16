#!/usr/bin/env python3
"""
STADVDB MCO1 - PostgreSQL Connection Verification Script
Tests database connectivity, verifies server version, and checks for nyc_taxi_source database.
Credentials are read securely from environment variables or data/source/.env.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg

# Load environment variables from .env in the same directory if it exists
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

host = os.getenv("PGHOST", "localhost")
port = int(os.getenv("PGPORT", "5432"))
user = os.getenv("PGUSER", "postgres")
password = os.getenv("PGPASSWORD", None)
default_db = os.getenv("PGDATABASE", "postgres")
target_db = os.getenv("SOURCE_DB", "nyc_taxi_source")

def test_connection():
    print(f"Connecting to PostgreSQL at {host}:{port} as user '{user}'...")
    try:
        # Connect to default database (e.g. postgres or MC01) to verify server access
        conn = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=default_db,
            autocommit=True
        )
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version_str = cur.fetchone()[0]
            print(f"[SUCCESS] Connected successfully!")
            print(f"Server version: {version_str}")
            
            # Check if target database nyc_taxi_source exists
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db,))
            exists = cur.fetchone() is not None
            if exists:
                print(f"[INFO] Database '{target_db}' ALREADY EXISTS.")
            else:
                print(f"[INFO] Database '{target_db}' does not exist yet.")
                print(f"Attempting to create database '{target_db}'...")
                cur.execute(f'CREATE DATABASE "{target_db}";')
                print(f"[SUCCESS] Database '{target_db}' created successfully!")
        conn.close()

        # Connect directly to target_db to verify access
        conn_target = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=target_db,
            autocommit=True
        )
        with conn_target.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            db, usr = cur.fetchone()
            print(f"[SUCCESS] Connected to target database '{db}' as '{usr}'!")
        conn_target.close()
        return True

    except psycopg.OperationalError as e:
        print(f"[ERROR] Connection failed: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
