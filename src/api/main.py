"""Read-only REST API over the PortfolioPulse database.

Run locally:
    uvicorn src.api.main:app --reload
Interactive docs (Swagger UI): http://localhost:8000/docs

Authentication is optional: if the API_KEY environment variable is set, every
route except /health requires a matching X-API-Key header; if it is unset the
API is open (the local demo default). /health stays open for container health checks.

Routes only validate input, call the repository, and shape the response.
SQL lives in src/api/repository.py; risk maths lives in src/analytics/risk.py.
There are no write endpoints: the pipeline is the only writer.
"""
import os
import secrets
from datetime import date
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.engine import Connection

from src.analytics.risk import calculate_cvar, calculate_var
from src.api import repository as repo
from src.api.schemas import (
    AllocationOut,
    Health,
    HoldingOut,
    ManagerOut,
    PriceOut,
    RankingOut,
    RiskOut,
)
from src.db import engine

app = FastAPI(
    title="PortfolioPulse API",
    version="1.0.0",
    description="Read-only access to manager performance, portfolio valuation, allocation drift and risk.",
)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(supplied: str | None = Security(_api_key_header)) -> None:
    """No-op when API_KEY is unset. Otherwise the header must match (constant-time compare)."""
    expected = os.getenv("API_KEY")
    if not expected:
        return
    if not supplied or not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="missing or invalid API key", headers={"WWW-Authenticate": "ApiKey"})


PROTECTED = [Depends(require_api_key)]

MIN_VALUE_POINTS = 3  # 3 daily values -> 2 returns, the least that gives a meaningful quantile


def get_conn() -> Iterator[Connection]:
    """One connection per request, always closed. Tests override this."""
    with engine.connect() as conn:
        yield conn


def _require_portfolio(conn: Connection, portfolio_id: int) -> None:
    if not repo.portfolio_exists(conn, portfolio_id):
        raise HTTPException(status_code=404, detail=f"portfolio {portfolio_id} not found")


@app.get("/health", response_model=Health, tags=["meta"])
def health(conn: Connection = Depends(get_conn)) -> Health:
    try:
        repo.ping(conn)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc.__class__.__name__}")
    return Health(status="ok", database="up")


@app.get("/managers", dependencies=PROTECTED, response_model=list[ManagerOut], tags=["managers"])
def managers(conn: Connection = Depends(get_conn)):
    return repo.list_managers(conn)


@app.get("/managers/rankings", dependencies=PROTECTED, response_model=list[RankingOut], tags=["managers"])
def rankings(
    quarter: str | None = Query(None, pattern=r"^\d{4}-Q[1-4]$", examples=["2026-Q3"]),
    conn: Connection = Depends(get_conn),
):
    """Managers ranked by portfolio return within each calendar quarter."""
    return repo.manager_rankings(conn, quarter)


@app.get("/portfolios/{portfolio_id}/holdings", dependencies=PROTECTED, response_model=list[HoldingOut], tags=["portfolios"])
def holdings(portfolio_id: int, conn: Connection = Depends(get_conn)):
    _require_portfolio(conn, portfolio_id)
    return repo.portfolio_holdings(conn, portfolio_id)


@app.get("/portfolios/{portfolio_id}/allocation", dependencies=PROTECTED, response_model=list[AllocationOut], tags=["portfolios"])
def allocation(portfolio_id: int, conn: Connection = Depends(get_conn)):
    _require_portfolio(conn, portfolio_id)
    return repo.portfolio_allocation(conn, portfolio_id)


@app.get("/portfolios/{portfolio_id}/risk", dependencies=PROTECTED, response_model=RiskOut, tags=["portfolios"])
def risk(
    portfolio_id: int,
    confidence: float = Query(0.95, gt=0, lt=1),
    method: Literal["historical", "parametric"] = "historical",
    conn: Connection = Depends(get_conn),
):
    """One-day Value at Risk and Expected Shortfall as positive loss fractions.

    Computed from the portfolio's daily value history (constant quantities).
    VaR uses the chosen method; CVaR is always historical, so with a short
    history and parametric VaR the CVaR can come out lower than the VaR.
    """
    _require_portfolio(conn, portfolio_id)
    values = repo.portfolio_value_series(conn, portfolio_id)
    if len(values) < MIN_VALUE_POINTS:
        raise HTTPException(
            status_code=409,
            detail=f"not enough price history: need at least {MIN_VALUE_POINTS} daily values, have {len(values)}",
        )
    returns = values.pct_change().dropna()
    return RiskOut(
        portfolio_id=portfolio_id,
        confidence=confidence,
        method=method,
        var=calculate_var(returns, confidence, method),
        cvar=calculate_cvar(returns, confidence),
        n_returns=len(returns),
        first_date=values.index[0].date(),
        last_date=values.index[-1].date(),
    )


@app.get("/prices/{ticker}", dependencies=PROTECTED, response_model=list[PriceOut], tags=["prices"])
def prices(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(500, ge=1, le=5000),
    conn: Connection = Depends(get_conn),
):
    """Daily OHLCV for one ticker, oldest first. With `limit`, the most recent rows in range."""
    ticker = ticker.upper()
    if not repo.ticker_exists(conn, ticker):
        raise HTTPException(status_code=404, detail=f"ticker {ticker} not found")
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must not be after end")
    return repo.price_history(conn, ticker, start, end, limit)
