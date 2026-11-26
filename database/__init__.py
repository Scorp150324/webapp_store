import os
import re
from threading import Lock

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text as sqlalchemy_text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

_MYSQL_TABLE_REFERENCE = re.compile(
    r"\b(FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][A-Za-z0-9_]*)",
    flags=re.IGNORECASE,
)


def _adapt_statement(statement, dialect_name="mysql"):
    if dialect_name != "mysql":
        raise RuntimeError("Only MySQL is supported")

    # MySQL table-name casing is filesystem-dependent. The schema dump uses
    # lowercase table names, so normalize references for Linux hosts while
    # leaving mixed-case column names unchanged.
    statement = _MYSQL_TABLE_REFERENCE.sub(
        lambda match: f"{match.group(1)} {match.group(2).lower()}", statement
    )
    statement = re.sub(r"\bILIKE\b", "LIKE", statement, flags=re.IGNORECASE)

    def replace_interval(match):
        operation = "DATE_SUB" if match.group(1) == "-" else "DATE_ADD"
        unit = match.group(3).upper().rstrip("S")
        return f"{operation}(CURRENT_TIMESTAMP, INTERVAL {match.group(2)} {unit})"

    return re.sub(
        r"\bCURRENT_TIMESTAMP\s*([+-])\s*INTERVAL\s*'(\d+)\s+(days?|hours?|minutes?)'",
        replace_interval,
        statement,
        flags=re.IGNORECASE,
    )


def text(statement):
    return sqlalchemy_text(_adapt_statement(statement, engine.dialect.name))


def insert_id(connection, statement, parameters, returning_column):
    result = connection.execute(text(statement), parameters)
    if result.lastrowid is None:
        raise RuntimeError("The MySQL insert did not return an auto-increment ID")
    return result.lastrowid


def product_search_subquery():
    columns = ("ProductName", "SKU", "Barcode", "Specifications")
    branches = [
        "SELECT ProductID FROM Products "
        f"WHERE IsDeleted = 0 AND {column} LIKE :search ESCAPE '='"
        for column in columns
    ]
    return " UNION ".join(branches)


def product_search_pattern(value):
    escaped = value.replace("=", "==").replace("%", "=%").replace("_", "=_")
    return f"{escaped}%"


database_url = os.environ.get("DATABASE_URL")
is_production = os.environ.get("FLASK_ENV", "").strip().lower() == "production"
if not database_url:
    if is_production:
        raise RuntimeError("DATABASE_URL must be configured in production")
    database_url = URL.create(
        "mysql+pymysql",
        username="root",
        host="localhost",
        port=3306,
        database="store_management_db",
        query={"charset": "utf8mb4"},
    )
else:
    database_url = make_url(database_url)
    if database_url.drivername == "mysql":
        database_url = database_url.set(drivername="mysql+pymysql")
    if database_url.drivername != "mysql+pymysql":
        raise RuntimeError("DATABASE_URL must use MySQL with PyMySQL")

connect_args = {"connect_timeout": 5}
engine = create_engine(
    database_url,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_customer_presence_schema_checked = False
_customer_presence_schema_lock = Lock()


def ensure_customer_presence_schema():
    """Add presence columns to an existing MySQL customer table once."""
    global _customer_presence_schema_checked
    if _customer_presence_schema_checked:
        return

    with _customer_presence_schema_lock:
        if _customer_presence_schema_checked:
            return
        table_name = "customers"
        with engine.begin() as connection:
            existing = {
                column["name"].lower()
                for column in inspect(connection).get_columns(table_name)
            }
            additions = {
                "isonline": "ALTER TABLE customers ADD COLUMN IsOnline TINYINT(1) NOT NULL DEFAULT 0",
                "lastseenat": "ALTER TABLE customers ADD COLUMN LastSeenAt DATETIME NULL",
            }
            for column_name, statement in additions.items():
                if column_name not in existing:
                    connection.exec_driver_sql(statement)

        _customer_presence_schema_checked = True

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
