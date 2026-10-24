"""Guards the README's SQL examples against schema drift.

Runs every query in sql/analytics_examples.sql against the real schema and
checks it executes and returns the documented columns. The test database
is empty here (pg_session rolls back), so this proves syntax and column
names, not figures; the figures in the README come from a seeded run.
"""
import re
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "analytics_examples.sql"

EXPECTED_COLUMNS = {
    1: ["quarter", "firm_name", "start_value", "end_value", "return_pct", "rank"],
    2: ["firm_name", "asset_class", "market_value", "actual_pct", "target_pct", "drift_pct"],
    3: ["firm_name", "ticker", "quantity", "cost_basis", "latest_close", "unrealized_gl", "gl_pct"],
    4: ["sector", "market_value", "pct_of_total", "dividends_received"],
}


def _load_queries() -> dict[int, str]:
    raw = SQL_PATH.read_text()
    parts = re.split(r"(?m)^-- (\d+)\. ", raw)
    # parts = [preamble, "1", body1, "2", body2, ...]
    return {int(parts[i]): "-- " + parts[i] + ". " + parts[i + 1].strip().rstrip(";")
            for i in range(1, len(parts), 2)}


def test_sql_file_contains_all_four_examples():
    assert sorted(_load_queries()) == [1, 2, 3, 4]


@pytest.mark.parametrize("number", sorted(EXPECTED_COLUMNS))
def test_query_runs_and_returns_documented_columns(pg_session, number):
    result = pg_session.execute(text(_load_queries()[number]))
    assert list(result.keys()) == EXPECTED_COLUMNS[number]