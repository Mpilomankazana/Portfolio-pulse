"""Database engine/session helpers, driven by DATABASE_URL."""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://de27four:de27four_pw@localhost:5432/portfolio_analytics",
)



def with_explicit_driver(url: str) -> str:
    """Make a plain postgresql:// (or postgres://) URL name the psycopg2 driver.

    requirements.txt installs psycopg2-binary. SQLAlchemy 2.0 used psycopg2 for a
    bare postgresql:// URL, but SQLAlchemy 2.1 defaults to psycopg (version 3),
    which is not installed, so a fresh install failed with
    "No module named 'psycopg'". Naming the driver removes the dependence on
    whichever default the installed SQLAlchemy version has. A URL that already
    names a driver (postgresql+psycopg://, postgresql+psycopg2://) is left alone.
    """
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg2")
        return parsed.render_as_string(hide_password=False)
    return url


engine = create_engine(with_explicit_driver(DATABASE_URL), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
