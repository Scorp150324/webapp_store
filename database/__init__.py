import os
import re

from dotenv import load_dotenv
from sqlalchemy import create_engine, text as sqlalchemy_text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

_IDENTIFIER_TOKEN = re.compile(
    r"'(?:''|[^'])*'|--[^\r\n]*|\"(?:\"\"|[^\"])*\"|"
    r":[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*"
)


def _quote_legacy_identifiers(statement):
    """Keep legacy mixed-case SQL identifiers compatible with PostgreSQL."""

    def quote(match):
        token = match.group(0)
        if token.startswith(("'", '"', "--", ":")):
            return token
        if token == "SKU" or (
            token[0].isupper()
            and token != token.upper()
            and any(character.islower() for character in token)
        ):
            return f'"{token}"'
        return token

    return _IDENTIFIER_TOKEN.sub(quote, statement)


def _adapt_statement(statement, dialect_name):
    if dialect_name == "mysql":
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
    return _quote_legacy_identifiers(statement)


def text(statement):
    return sqlalchemy_text(_adapt_statement(statement, engine.dialect.name))


def insert_id(connection, statement, parameters, returning_column):
    if engine.dialect.name == "mysql":
        result = connection.execute(text(statement), parameters)
        if result.lastrowid is None:
            raise RuntimeError("The MySQL insert did not return an auto-increment ID")
        return result.lastrowid
    return connection.execute(
        text(f"{statement} RETURNING {returning_column}"), parameters
    ).scalar_one()


def product_search_subquery():
    columns = ("ProductName", "SKU", "Barcode", "Specifications")
    if engine.dialect.name == "mysql":
        expressions = list(columns)
    else:
        expressions = [f"lower({column})" for column in columns]
    branches = [
        "SELECT ProductID FROM Products "
        f"WHERE IsDeleted = 0 AND {expression} LIKE :search ESCAPE '='"
        for expression in expressions
    ]
    return " UNION ".join(branches)


def product_search_pattern(value):
    escaped = value.replace("=", "==").replace("%", "=%").replace("_", "=_")
    if engine.dialect.name != "mysql":
        escaped = escaped.lower()
    return f"{escaped}%"


database_url = os.environ.get("DATABASE_URL")
is_production = (
    os.environ.get("FLASK_ENV", "").strip().lower() == "production"
    or bool(os.environ.get("VERCEL"))
)
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
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    database_url = make_url(database_url)
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+psycopg")
    elif database_url.drivername == "mysql":
        database_url = database_url.set(drivername="mysql+pymysql")
    if database_url.drivername not in {"postgresql+psycopg", "mysql+pymysql"}:
        raise RuntimeError(
            "DATABASE_URL must use PostgreSQL with psycopg or MySQL with PyMySQL"
        )
    if is_production and database_url.drivername == "postgresql+psycopg":
        query = dict(database_url.query)
        query["sslmode"] = "require"
        database_url = database_url.set(query=query)

connect_args = (
    {"prepare_threshold": None}
    if database_url.drivername == "postgresql+psycopg"
    else {"connect_timeout": 5}
)
engine = create_engine(
    database_url,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()