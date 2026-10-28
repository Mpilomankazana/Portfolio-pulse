"""Unit tests for the REST API routes. The repository is replaced, so no
database is needed: these check routing, validation, error codes and the
shape of responses. SQL correctness is covered by tests/integration/test_api_queries.py.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.analytics.risk import calculate_cvar, calculate_var
from src.api import main


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[main.get_conn] = lambda: object()
    monkeypatch.setattr(main.repo, "portfolio_exists", lambda conn, pid: pid == 1)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(main.repo, "ping", lambda conn: True)
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "up"}


def test_health_503_when_database_is_down(client, monkeypatch):
    def down(conn):
        raise ConnectionError("refused")
    monkeypatch.setattr(main.repo, "ping", down)
    r = client.get("/health")
    assert r.status_code == 503 and "ConnectionError" in r.json()["detail"]


def test_managers_serialises_decimals_and_nulls(client, monkeypatch):
    from decimal import Decimal
    monkeypatch.setattr(main.repo, "list_managers", lambda conn: [
        {"manager_id": 1, "firm_name": "A", "strategy_type": None, "portfolio_id": None,
         "benchmark": None, "allocation_pct": Decimal("50.00")},
    ])
    body = client.get("/managers").json()
    assert body == [{"manager_id": 1, "firm_name": "A", "strategy_type": None,
                     "portfolio_id": None, "benchmark": None, "allocation_pct": 50.0}]


def test_rankings_passes_quarter_through_and_validates_format(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(main.repo, "manager_rankings", lambda conn, q=None: seen.setdefault("q", q) and [])
    assert client.get("/managers/rankings?quarter=2026-Q3").status_code == 200
    assert seen["q"] == "2026-Q3"
    for bad in ("2026Q3", "2026-Q5", "26-Q1", "abc"):
        assert client.get(f"/managers/rankings?quarter={bad}").status_code == 422, bad


@pytest.mark.parametrize("path", ["holdings", "allocation", "risk"])
def test_unknown_portfolio_is_404(client, path):
    r = client.get(f"/portfolios/999/{path}")
    assert r.status_code == 404 and "999" in r.json()["detail"]


def test_non_integer_portfolio_id_is_422(client):
    assert client.get("/portfolios/abc/holdings").status_code == 422


def _values(n=60, seed=3):
    rng = np.random.default_rng(seed)
    v = 1_000_000 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    return pd.Series(v, index=pd.bdate_range("2026-08-03", periods=n), name="value")


def test_risk_matches_the_analytics_functions(client, monkeypatch):
    values = _values()
    monkeypatch.setattr(main.repo, "portfolio_value_series", lambda conn, pid: values)
    returns = values.pct_change().dropna()

    body = client.get("/portfolios/1/risk?confidence=0.95").json()

    assert body["var"] == pytest.approx(calculate_var(returns, 0.95, "historical"))
    assert body["cvar"] == pytest.approx(calculate_cvar(returns, 0.95))
    assert body["n_returns"] == 59 and body["method"] == "historical" and body["horizon"] == "1 day"
    assert body["first_date"] == "2026-08-03" and body["last_date"] == values.index[-1].date().isoformat()
    assert body["cvar"] >= body["var"]


def test_risk_parametric_method(client, monkeypatch):
    values = _values()
    monkeypatch.setattr(main.repo, "portfolio_value_series", lambda conn, pid: values)
    returns = values.pct_change().dropna()
    body = client.get("/portfolios/1/risk?method=parametric&confidence=0.99").json()
    assert body["var"] == pytest.approx(calculate_var(returns, 0.99, "parametric"))


def test_risk_with_too_little_history_is_409(client, monkeypatch):
    monkeypatch.setattr(main.repo, "portfolio_value_series", lambda conn, pid: _values(2))
    r = client.get("/portfolios/1/risk")
    assert r.status_code == 409 and "not enough price history" in r.json()["detail"]


@pytest.mark.parametrize("qs", ["confidence=0", "confidence=1", "confidence=-0.1", "confidence=2", "method=monte-carlo"])
def test_risk_rejects_bad_parameters(client, monkeypatch, qs):
    monkeypatch.setattr(main.repo, "portfolio_value_series", lambda conn, pid: _values())
    assert client.get(f"/portfolios/1/risk?{qs}").status_code == 422


def test_prices_uppercases_ticker_and_checks_it_exists(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(main.repo, "ticker_exists", lambda conn, t: t == "AAPL")

    def history(conn, t, start, end, limit):
        seen.update(t=t, start=start, end=end, limit=limit)
        return [{"price_date": date(2026, 10, 1), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]
    monkeypatch.setattr(main.repo, "price_history", history)

    r = client.get("/prices/aapl?start=2026-10-01&limit=7")
    assert r.status_code == 200 and r.json()[0]["close"] == 1.5
    assert seen == {"t": "AAPL", "start": date(2026, 10, 1), "end": None, "limit": 7}
    assert client.get("/prices/nope").status_code == 404


def test_prices_validates_range_and_limit(client, monkeypatch):
    monkeypatch.setattr(main.repo, "ticker_exists", lambda conn, t: True)
    monkeypatch.setattr(main.repo, "price_history", lambda *a: [])
    assert client.get("/prices/AAPL?start=2026-10-20&end=2026-10-01").status_code == 422
    assert client.get("/prices/AAPL?limit=0").status_code == 422
    assert client.get("/prices/AAPL?limit=5001").status_code == 422
    assert client.get("/prices/AAPL?start=not-a-date").status_code == 422


def test_openapi_documents_every_route():
    paths = set(main.app.openapi()["paths"])
    assert paths == {"/health", "/managers", "/managers/rankings", "/portfolios/{portfolio_id}/holdings",
                     "/portfolios/{portfolio_id}/allocation", "/portfolios/{portfolio_id}/risk", "/prices/{ticker}"}


def test_api_is_read_only():
    methods = {m for route in main.app.routes if hasattr(route, "methods") for m in route.methods}
    assert methods <= {"GET", "HEAD", "OPTIONS"}
