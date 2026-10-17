from sqlalchemy import create_engine, URL
from config import SOURCE_DB, WAREHOUSE_DB, IS_ETL_DEVELOPER


def create_database_engine(credentials):
    url = URL.create(
        drivername="postgresql+psycopg",
        username=credentials["username"],
        password=credentials["password"],
        host=credentials["host"],
        port=credentials["port"],
        database=credentials["database"],
    )

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
    )


source_engine = create_database_engine(SOURCE_DB)
warehouse_engine = create_database_engine(WAREHOUSE_DB)

database_engines = []
if IS_ETL_DEVELOPER == 1:
    database_engines.append(("Source Database", source_engine))
database_engines.append(("Data Warehouse", warehouse_engine))


def test_connections():
    for name, engine in database_engines:
        try:
            with engine.connect() as connection:
                result = connection.exec_driver_sql(
                    "SELECT current_database(), current_user"
                )
                database, user = result.fetchone()

                print(f"[SUCCESS] {name}")
                print(f"Database: {database}")
                print(f"User: {user}")
                print(f"\n")

        except Exception as error:
            print(f"[FAILED] {name}: {error}")
            print(f"\n")


test_connections()