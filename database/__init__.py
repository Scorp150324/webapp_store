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


def text(statement):
    return sqlalchemy_text(_quote_legacy_identifiers(statement))


database_url = os.environ.get("DATABASE_URL")
is_production = (
    os.environ.get("FLASK_ENV", "").strip().lower() == "production"
    or bool(os.environ.get("VERCEL"))
)
if not database_url:
    if is_production:
        raise RuntimeError("DATABASE_URL must be configured in production")
    database_url = URL.create(
        "postgresql+psycopg",
        username="postgres",
        host="localhost",
        port=5432,
        database="store_management_db",
    )
else:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    database_url = make_url(database_url)
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+psycopg")
    if database_url.drivername != "postgresql+psycopg":
        raise RuntimeError("DATABASE_URL must use PostgreSQL with the psycopg driver")
    if is_production:
        query = dict(database_url.query)
        query["sslmode"] = "require"
        database_url = database_url.set(query=query)

engine = create_engine(
    database_url,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()