"""Fixtures for integration tests that need a real PostgreSQL 16 instance.

Kept separate from tests/conftest.py on purpose: the existing unit test
suite (test_clean.py, test_extract.py, test_loader.py) mocks the DB
engine and never needs real Postgres — don't merge these fixtures into
that file, or unit tests would start requiring Docker to run.

Mechanism chosen: point at the docker-compose `postgres_test` service
(see docker-compose.yml) rather than testcontainers-python. Simpler and
adds no new dependency, at the cost of a manual step before running
these tests:

    docker compose up -d postgres_test
    TEST_DATABASE_URL=postgresql://de27four_test:de27four_test_pw@localhost:5433/portfolio_analytics_test \
        pytest -m integration

(See README.md's Setup section for the same instructions.)

pg_engine applies sql/schema.sql itself before any test runs, rather
than relying solely on docker-entrypoint-initdb.d (which only runs
against a fresh, empty data directory) — so these tests are correct
whether postgres_test is a brand-new container or one that's been
reused across runs. Every statement in schema.sql is written to be
idempotent (CREATE ... IF NOT EXISTS / ADD COLUMN IF NOT EXISTS), so
reapplying it against an already-migrated database is a safe no-op.
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "sql" / "schema.sql"


@pytest.fixture(scope="session")
def pg_engine():
    """Session-scoped SQLAlchemy engine against the integration test database.

    Deliberately reads a separate TEST_DATABASE_URL env var rather than
    falling back to src.db.DATABASE_URL (or its default), so a missing
    env var can never silently point integration tests at a real
    dev/prod database — it's a hard failure instead.
    """
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set. Integration tests need a "
            "dedicated test database — start it with "
            "`docker compose up -d postgres_test` and set "
            "TEST_DATABASE_URL to point at it (see README.md Setup). "
            "Refusing to fall back to the regular DATABASE_URL, since "
            "that could point at a real dev/prod database."
        )

    engine = create_engine(test_database_url, future=True)

    schema_sql = SCHEMA_PATH.read_text()
    with engine.begin() as conn:
        conn.execute(text(schema_sql))

    yield engine

    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    """Function-scoped connection wrapped in a transaction that's rolled
    back after the test, so no test leaves data behind for the next one.

    Yields a SQLAlchemy Connection (not a Session) bound to that
    transaction — callers use conn.execute(text(...), params) directly,
    matching the style src/load/loader.py already uses for raw SQL.
    """
    connection = pg_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def seed_managers_and_assets(pg_session):
    """Insert a small, known set of managers/portfolios/assets for tests
    of upsert_market_prices and future analytics functions to build on.

    Returns a dict of the inserted ids, keyed by a short mnemonic name,
    so a test can reference e.g. ids["manager"] rather than a magic
    number. Inserted rows live inside pg_session's transaction, so they
    disappear at the end of the test along with everything else it did.
    """
    manager_id = pg_session.execute(
        text(
            "INSERT INTO managers (firm_name, strategy_type) "
            "VALUES (:firm_name, :strategy_type) RETURNING manager_id"
        ),
        {"firm_name": "Test Capital Partners", "strategy_type": "Long/Short Equity"},
    ).scalar_one()

    portfolio_id = pg_session.execute(
        text(
            "INSERT INTO portfolios (manager_id, benchmark, allocation_pct) "
            "VALUES (:manager_id, :benchmark, :allocation_pct) RETURNING portfolio_id"
        ),
        {"manager_id": manager_id, "benchmark": "S&P 500", "allocation_pct": 100.00},
    ).scalar_one()

    aapl_id = pg_session.execute(
        text(
            "INSERT INTO assets (ticker, asset_class, sector) "
            "VALUES (:ticker, :asset_class, :sector) RETURNING asset_id"
        ),
        {"ticker": "AAPL", "asset_class": "Equities", "sector": "Technology"},
    ).scalar_one()

    msft_id = pg_session.execute(
        text(
            "INSERT INTO assets (ticker, asset_class, sector) "
            "VALUES (:ticker, :asset_class, :sector) RETURNING asset_id"
        ),
        {"ticker": "MSFT", "asset_class": "Equities", "sector": "Technology"},
    ).scalar_one()

    return {
        "manager": manager_id,
        "portfolio": portfolio_id,
        "aapl": aapl_id,
        "msft": msft_id,
    }