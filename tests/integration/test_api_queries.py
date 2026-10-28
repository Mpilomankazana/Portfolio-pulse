"""API repository SQL and routes against a real PostgreSQL schema.

Builds a small, hand-checkable dataset inside the rolled-back test
transaction, then asserts exact figures.

Dataset: one portfolio, holdings AAPL x10 (cost 100) and MSFT x5 (cost 200).
Closes by date:            AAPL   MSFT   portfolio value
    2026-09-30 (Q3 end)     110    190    10*110 + 5*190 = 2050
    2026-10-01 (Q4 start)   120    200    10*120 + 5*200 = 2200
    2026-10-02              90     220    10*90  + 5*220 = 2000
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api import main, repository as repo

pytestmark = pytest.mark.integration

PRICES = {
    "aapl": [("2026-09-29", 100), ("2026-09-30", 110), ("2026-10-01", 120), ("2026-10-02", 90)],
    "msft": [("2026-09-29", 180), ("2026-09-30", 190), ("2026-10-01", 200), ("2026-10-02", 220)],
}


@pytest.fixture
def data(pg_session, seed_managers_and_assets):
    ids = seed_managers_and_assets
    pg_session.execute(text("UPDATE assets SET asset_class='Equities' WHERE asset_id IN (:a, :m)"),
                       {"a": ids["aapl"], "m": ids["msft"]})
    cash = pg_session.execute(text(
        "INSERT INTO assets (ticker, asset_class) VALUES ('CASHX', 'Cash') RETURNING asset_id")).scalar_one()
    for key, qty, cost in (("aapl", 10, 100), ("msft", 5, 200)):
        pg_session.execute(text(
            "INSERT INTO portfolio_holdings (portfolio_id, asset_id, weight_pct, quantity, cost_basis) "
            "VALUES (:p, :a, 50, :q, :c)"), {"p": ids["portfolio"], "a": ids[key], "q": qty, "c": cost})
        for d, close in PRICES[key]:
            pg_session.execute(text(
                "INSERT INTO market_prices (asset_id, price_date, open, high, low, close, volume) "
                "VALUES (:a, :d, :c, :c, :c, :c, 1000)"), {"a": ids[key], "d": d, "c": close})
    pg_session.execute(text(
        "INSERT INTO portfolio_targets (portfolio_id, asset_class, target_pct) VALUES (:p,'Equities',80), (:p,'Cash',20)"),
        {"p": ids["portfolio"]})

    # A second manager holding only MSFT x10, so rank order can flip between quarters.
    m2 = pg_session.execute(text(
        "INSERT INTO managers (firm_name, strategy_type) VALUES ('Rival Fund', 'Value') RETURNING manager_id")).scalar_one()
    p2 = pg_session.execute(text(
        "INSERT INTO portfolios (manager_id, benchmark, allocation_pct) VALUES (:m, 'S&P 500', 0) RETURNING portfolio_id"),
        {"m": m2}).scalar_one()
    pg_session.execute(text(
        "INSERT INTO portfolio_holdings (portfolio_id, asset_id, weight_pct, quantity, cost_basis) "
        "VALUES (:p, :a, 100, 10, 150)"), {"p": p2, "a": ids["msft"]})
    return {**ids, "cash": cash, "rival_portfolio": p2}


@pytest.fixture
def client(pg_session):
    main.app.dependency_overrides[main.get_conn] = lambda: pg_session
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_ping_and_managers(pg_session, data):
    assert repo.ping(pg_session) is True
    rows = [r for r in repo.list_managers(pg_session) if r["manager_id"] == data["manager"]]
    assert len(rows) == 1 and rows[0]["firm_name"] == "Test Capital Partners"
    assert rows[0]["portfolio_id"] == data["portfolio"]


def test_rankings_per_quarter_hand_calculated(pg_session, data):
    rows = {r["quarter"]: r for r in repo.manager_rankings(pg_session)
            if r["firm_name"] == "Test Capital Partners"}
    # Q3: first close 09-29 (10*100 + 5*180 = 1900) -> last close 09-30 (2050): +7.89%
    assert float(rows["2026-Q3"]["start_value"]) == 1900.00 and float(rows["2026-Q3"]["end_value"]) == 2050.00
    assert float(rows["2026-Q3"]["return_pct"]) == pytest.approx(7.89)
    # Q4: first close 10-01 (2200) -> last close 10-02 (2000): -9.09%
    assert float(rows["2026-Q4"]["return_pct"]) == pytest.approx(-9.09)
    assert rows["2026-Q3"]["rank"] == 1


def test_rank_order_flips_between_quarters(pg_session, data):
    """Rival (MSFT only): Q3 1800 -> 1900 = +5.56%, Q4 2000 -> 2200 = +10.00%.
    Test Capital: Q3 +7.89%, Q4 -9.09%. So Test Capital leads Q3, Rival leads Q4."""
    rows = {(r["quarter"], r["firm_name"]): r for r in repo.manager_rankings(pg_session)
            if r["firm_name"] in ("Test Capital Partners", "Rival Fund")}
    assert float(rows[("2026-Q3", "Rival Fund")]["return_pct"]) == pytest.approx(5.56)
    assert float(rows[("2026-Q4", "Rival Fund")]["return_pct"]) == pytest.approx(10.00)
    assert rows[("2026-Q3", "Test Capital Partners")]["rank"] < rows[("2026-Q3", "Rival Fund")]["rank"]
    assert rows[("2026-Q4", "Rival Fund")]["rank"] < rows[("2026-Q4", "Test Capital Partners")]["rank"]
    # results come back ordered by quarter then rank
    q4 = [r for r in repo.manager_rankings(pg_session, "2026-Q4") if r["firm_name"] in ("Test Capital Partners", "Rival Fund")]
    assert [r["firm_name"] for r in q4] == ["Rival Fund", "Test Capital Partners"]


def test_rankings_quarter_filter(pg_session, data):
    only = repo.manager_rankings(pg_session, "2026-Q4")
    assert {r["quarter"] for r in only} == {"2026-Q4"}
    assert repo.manager_rankings(pg_session, "1999-Q1") == []


def test_holdings_valued_at_latest_close(pg_session, data):
    rows = {r["ticker"]: r for r in repo.portfolio_holdings(pg_session, data["portfolio"])}
    assert float(rows["AAPL"]["market_value"]) == 900.00       # 10 * 90
    assert float(rows["AAPL"]["unrealized_gl"]) == -100.00      # (90-100)*10
    assert float(rows["AAPL"]["gl_pct"]) == -10.00
    assert float(rows["MSFT"]["market_value"]) == 1100.00       # 5 * 220
    assert float(rows["MSFT"]["unrealized_gl"]) == 100.00       # (220-200)*5
    assert rows["MSFT"]["latest_price_date"] == date(2026, 10, 2)


def test_allocation_includes_empty_target_class_as_zero(pg_session, data):
    rows = {r["asset_class"]: r for r in repo.portfolio_allocation(pg_session, data["portfolio"])}
    assert float(rows["Equities"]["actual_pct"]) == 100.00      # all value is equities
    assert float(rows["Equities"]["drift_pct"]) == 20.00        # 100 - 80
    assert float(rows["Cash"]["market_value"]) == 0.00          # target 20, nothing held
    assert float(rows["Cash"]["drift_pct"]) == -20.00


def test_value_series_matches_hand_calculation(pg_session, data):
    s = repo.portfolio_value_series(pg_session, data["portfolio"])
    assert [round(v) for v in s] == [1900, 2050, 2200, 2000]
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]


def test_value_series_drops_dates_where_a_holding_has_no_price(pg_session, data):
    pg_session.execute(text(
        "DELETE FROM market_prices WHERE asset_id = :a AND price_date = '2026-10-01'"), {"a": data["msft"]})
    s = repo.portfolio_value_series(pg_session, data["portfolio"])
    assert "2026-10-01" not in list(s.index.strftime("%Y-%m-%d"))
    assert len(s) == 3


def test_price_history_range_limit_and_order(pg_session, data):
    all_rows = repo.price_history(pg_session, "AAPL", None, None, 500)
    assert [float(r["close"]) for r in all_rows] == [100, 110, 120, 90]
    ranged = repo.price_history(pg_session, "AAPL", date(2026, 9, 30), date(2026, 10, 1), 500)
    assert [float(r["close"]) for r in ranged] == [110, 120]
    newest_two = repo.price_history(pg_session, "AAPL", None, None, 2)
    assert [float(r["close"]) for r in newest_two] == [120, 90]       # most recent 2, oldest first
    assert repo.ticker_exists(pg_session, "AAPL") and not repo.ticker_exists(pg_session, "ZZZZ")


def test_full_http_stack_against_real_database(client, data):
    pid = data["portfolio"]
    assert client.get("/health").json() == {"status": "ok", "database": "up"}
    holdings = client.get(f"/portfolios/{pid}/holdings").json()
    assert {h["ticker"] for h in holdings} == {"AAPL", "MSFT"}
    risk = client.get(f"/portfolios/{pid}/risk?confidence=0.9").json()
    # returns: +7.89%, +7.32%, -9.09%; the 10% quantile falls between the worst and middle returns
    assert risk["n_returns"] == 3 and risk["var"] > 0.05 and risk["cvar"] >= risk["var"]
    assert client.get(f"/prices/aapl?limit=1").json()[0]["close"] == 90
