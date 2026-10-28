"""Pydantic response models for the REST API."""
from datetime import date
from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    database: str


class ManagerOut(BaseModel):
    manager_id: int
    firm_name: str
    strategy_type: str | None = None
    portfolio_id: int | None = None
    benchmark: str | None = None
    allocation_pct: float | None = None


class RankingOut(BaseModel):
    quarter: str
    firm_name: str
    start_value: float
    end_value: float
    return_pct: float
    rank: int


class HoldingOut(BaseModel):
    ticker: str
    asset_class: str
    sector: str | None = None
    quantity: float | None = None
    cost_basis: float | None = None
    latest_close: float
    latest_price_date: date
    market_value: float | None = None
    unrealized_gl: float | None = None
    gl_pct: float | None = None


class AllocationOut(BaseModel):
    asset_class: str
    market_value: float
    actual_pct: float | None = None
    target_pct: float | None = None
    drift_pct: float | None = None


class RiskOut(BaseModel):
    portfolio_id: int
    horizon: str = "1 day"
    confidence: float
    method: Literal["historical", "parametric"]
    var: float
    cvar: float
    n_returns: int
    first_date: date
    last_date: date


class PriceOut(BaseModel):
    price_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
