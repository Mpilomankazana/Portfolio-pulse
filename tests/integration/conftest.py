"""Fixtures for integration tests that need a real PostgreSQL 16 instance.

Kept separate from tests/conftest.py on purpose: the existing unit test
suite (test_clean.py, test_extract.py, test_loader.py) mocks the DB
engine and never needs real Postgres — don't merge these fixtures into
that file, or unit tests would start requiring Docker to run.

# TODO: implement, in this order:
#   1. Decide the mechanism for spinning up Postgres for tests. Two
#      common options:
#      a) testcontainers-python's PostgresContainer — spins up/tears down
#         a disposable Postgres 16 container per test session automatically.
#         Add `testcontainers` to requirements.txt if you go this route.
#      b) Point at the existing docker-compose `postgres` service (the one
#         already defined in docker-compose.yml) and require the developer
#         to `docker compose up -d postgres` before running integration
#         tests. Simpler, but couples test runs to a manual step — document
#         that clearly in the README if chosen.
#   2. A session-scoped `pg_engine` fixture: create a SQLAlchemy engine
#      pointed at the test database (use a distinct DB name/URL from the
#      one src/db.py's DATABASE_URL defaults to, so integration tests never
#      touch a real dev/prod database by accident).
#   3. Apply sql/schema.sql against the test database in this fixture,
#      before any test runs (e.g. via engine.execute or a subprocess call
#      to psql -f sql/schema.sql).
#   4. A function-scoped `pg_session` fixture that wraps each test in a
#      transaction and rolls it back after the test (SQLAlchemy's
#      connection.begin() + rollback pattern), so tests don't leave data
#      behind for the next test.
#   5. A `seed_managers_and_assets` fixture (or similar) that inserts a
#      small set of known rows (a couple of managers, portfolios, assets)
#      via pg_session, for tests of upsert_market_prices and future
#      analytics functions to build on.
#   6. Mark integration tests with @pytest.mark.integration and register
#      that marker in a pytest.ini/pyproject.toml `[tool.pytest.ini_options]
#      markers` section, so `pytest -m "not integration"` can run the fast
#      unit suite alone (e.g. in CI without Docker) while
#      `pytest -m integration` runs the full thing.
"""
import pytest


@pytest.fixture(scope="session")
def pg_engine():
    raise NotImplementedError("TODO: implement Postgres test engine fixture")


@pytest.fixture
def pg_session(pg_engine):
    raise NotImplementedError("TODO: implement transactional test session fixture")
