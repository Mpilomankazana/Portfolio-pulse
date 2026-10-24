"""Integration tests for tests/integration/conftest.py's own fixtures.

Requires a real Postgres instance — see that file's module docstring
for how to point TEST_DATABASE_URL at one. Not a test of application
code; this exists to prove the fixtures themselves behave as documented
(schema applied, transactions roll back, seed data has the right shape)
before other integration test suites build on top of them.
"""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


class TestPgEngine:
    def test_schema_is_applied(self, pg_engine):
        with pg_engine.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            }
        expected = {
            "managers", "portfolios", "assets", "market_prices",
            "portfolio_holdings", "dividends", "portfolio_targets",
        }
        assert expected.issubset(tables)

    def test_sector_column_exists_on_assets(self, pg_engine):
        with pg_engine.connect() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'assets'"
                    )
                )
            }
        assert "sector" in columns


class TestPgSession:
    def test_insert_is_visible_within_the_same_session(self, pg_session):
        pg_session.execute(
            text(
                "INSERT INTO managers (firm_name, strategy_type) "
                "VALUES ('Rollback Co', 'Macro')"
            )
        )
        count = pg_session.execute(
            text("SELECT COUNT(*) FROM managers WHERE firm_name = 'Rollback Co'")
        ).scalar_one()
        assert count == 1

    def test_insert_does_not_persist_across_tests(self, pg_session):
        # If the previous test's rollback didn't work, this row would
        # still be here.
        count = pg_session.execute(
            text("SELECT COUNT(*) FROM managers WHERE firm_name = 'Rollback Co'")
        ).scalar_one()
        assert count == 0


class TestSeedManagersAndAssets:
    def test_returns_ids_for_all_seeded_rows(self, seed_managers_and_assets):
        ids = seed_managers_and_assets
        assert set(ids.keys()) == {"manager", "portfolio", "aapl", "msft"}
        assert all(isinstance(v, int) for v in ids.values())

    def test_seeded_portfolio_references_seeded_manager(
        self, pg_session, seed_managers_and_assets
    ):
        ids = seed_managers_and_assets
        manager_id = pg_session.execute(
            text("SELECT manager_id FROM portfolios WHERE portfolio_id = :pid"),
            {"pid": ids["portfolio"]},
        ).scalar_one()
        assert manager_id == ids["manager"]

    def test_seeded_assets_have_distinct_tickers(self, pg_session, seed_managers_and_assets):
        ids = seed_managers_and_assets
        tickers = pg_session.execute(
            text("SELECT ticker FROM assets WHERE asset_id IN (:a, :b)"),
            {"a": ids["aapl"], "b": ids["msft"]},
        ).scalars().all()
        assert set(tickers) == {"AAPL", "MSFT"}