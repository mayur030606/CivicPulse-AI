"""SQLAlchemy engine, session factory and FastAPI database dependency.

The connection string is read from ``DATABASE_URL`` (see ``backend/.env``).
The individual ``DB_*`` settings are kept as a fallback for local setups that
do not define a full URL.

No credentials are ever placed in this file or returned by the API.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Driver: PyMySQL. ``mysql://`` URLs are normalised to ``mysql+pymysql://``
# in Settings.sqlalchemy_database_url.
engine: Engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=10,
    future=True,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


def get_db() -> Generator[Session, None, None]:
    """Reusable FastAPI dependency that yields one session per request."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_connection() -> None:
    """Run a lightweight query. Raises SQLAlchemyError when unreachable."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
