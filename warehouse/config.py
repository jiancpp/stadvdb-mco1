import os
from dotenv import load_dotenv

load_dotenv()

SOURCE_DB = {
    "host": os.getenv("PGHOST"),
    "port": int(os.getenv("PGPORT", 5432)),
    "database": os.getenv("SOURCE_DB"),
    "username": os.getenv("PGUSER"),
    "password": os.getenv("SOURCE_DB_PASSWORD"),
}

WAREHOUSE_DB = {
    "host": os.getenv("WAREHOUSE_DB_HOST"),
    "port": int(os.getenv("WAREHOUSE_DB_PORT", 5432)),
    "database": os.getenv("WAREHOUSE_DB_NAME"),
    "username": os.getenv("WAREHOUSE_DB_USER"),
    "password": os.getenv("WAREHOUSE_DB_PASSWORD"),
}

IS_ETL_DEVELOPER = os.getenv("IS_ETL_DEVELOPER")