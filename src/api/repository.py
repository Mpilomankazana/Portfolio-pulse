"""All SQL for the read-only REST API lives here.

Every function takes an open SQLAlchemy Connection and returns plain Python
data (dicts / DataFrame), so the route handlers in main.py contain no SQL
and these queries can be tested against a real database in isolation.

The ranking, allocation and valuation queries are the same ones documented
in sql/analytics_examples.sql, parameterised by portfolio where needed.
"""
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


def _rows(result) -> list[dict]:
    return [dict(r) for r in result.mappings().all()]


def ping(conn: Connection) -> bool:
    return conn.execute(text("SELECT 1")).scalar() == 1


def list_managers(conn: Connection) -> list[dict]:
    return _rows(conn.execute(text(
        """
        SELECT m.manager_id, m.firm_name, m.strategy_type,
               p.portfolio_id, p.benchmark, p.allocation_pct
        FROM managers m
        LEFT JOIN portfolios p ON p.manager_id = m.manager_id
        ORDER BY m.manager_id, p.portfolio_id
        """
    )))


def manager_rankings(conn: Connection, quarter: str | None = None) -> list[dict]:
    """Constant-quantity portfolio return per manager per calendar quarter,
    ranked within each quarter. quarter is like '2026-Q3', or None for all."""
    return _rows(conn.execute(text(
        """
        WITH q AS (
            SELECT asset_id,
                   date_trunc('quarter', price_date)::date AS quarter,
                   (array_agg(close ORDER BY price_date ASC))[1]  AS start_close,
                   (array_agg(close ORDER BY price_date DESC))[1] AS end_close
            FROM market_prices
            GROUP BY asset_id, date_trunc('quarter', price_date)
        ),
        ranked AS (
            SELECT to_char(q.quarter, 'YYYY"-Q"Q') AS quarter,
                   m.firm_name,
                   SUM(h.quantity * q.start_close) AS start_value,
                   SUM(h.quantity * q.end_close)   AS end_value,
                   (SUM(h.quantity * q.end_close) / SUM(h.quantity * q.start_close) - 1) * 100 AS return_pct,
                   RANK() OVER (PARTITION BY q.quarter
                                ORDER BY SUM(h.quantity * q.end_close)
                                       / SUM(h.quantity * q.start_close) DESC) AS rank
            FROM portfolio_holdings h
            JOIN portfolios p ON p.portfolio_id = h.portfolio_id
            JOIN managers   m ON m.manager_id   = p.manager_id
            JOIN q            ON q.asset_id     = h.asset_id
            GROUP BY q.quarter, m.firm_name
        )
        SELECT quarter, firm_name,
               round(start_value, 2) AS start_value,
               round(end_value, 2)   AS end_value,
               round(return_pct, 2)  AS return_pct,
               rank
        FROM ranked
        WHERE CAST(:quarter AS TEXT) IS NULL OR quarter = :quarter
        ORDER BY quarter, rank
        """
    ), {"quarter": quarter}))


def portfolio_exists(conn: Connection, portfolio_id: int) -> bool:
    return conn.execute(
        text("SELECT 1 FROM portfolios WHERE portfolio_id = :p"), {"p": portfolio_id}
    ).first() is not None


def portfolio_holdings(conn: Connection, portfolio_id: int) -> list[dict]:
    """Holdings valued at each asset's latest close, with unrealized gain/loss."""
    return _rows(conn.execute(text(
        """
        WITH latest AS (
            SELECT DISTINCT ON (asset_id) asset_id, close, price_date
            FROM market_prices
            ORDER BY asset_id, price_date DESC
        )
        SELECT a.ticker, a.asset_class, a.sector,
               h.quantity, h.cost_basis,
               l.close AS latest_close, l.price_date AS latest_price_date,
               round(h.quantity * l.close, 2)                    AS market_value,
               round((l.close - h.cost_basis) * h.quantity, 2)   AS unrealized_gl,
               round((l.close / h.cost_basis - 1) * 100, 2)      AS gl_pct
        FROM portfolio_holdings h
        JOIN assets a ON a.asset_id = h.asset_id
        JOIN latest l ON l.asset_id = h.asset_id
        WHERE h.portfolio_id = :p
        ORDER BY market_value DESC NULLS LAST, a.ticker
        """
    ), {"p": portfolio_id}))


def portfolio_allocation(conn: Connection, portfolio_id: int) -> list[dict]:
    """Actual vs target allocation by asset class at latest prices.

    FULL OUTER JOIN so a target class with no holdings shows as 0% actual,
    and a held class with no target shows with a NULL target.
    """
    return _rows(conn.execute(text(
        """
        WITH latest AS (
            SELECT DISTINCT ON (asset_id) asset_id, close
            FROM market_prices
            ORDER BY asset_id, price_date DESC
        ),
        v AS (
            SELECT a.asset_class, SUM(h.quantity * l.close) AS market_value
            FROM portfolio_holdings h
            JOIN assets a ON a.asset_id = h.asset_id
            JOIN latest l ON l.asset_id = h.asset_id
            WHERE h.portfolio_id = :p
            GROUP BY a.asset_class
        ),
        t AS (
            SELECT asset_class, target_pct FROM portfolio_targets WHERE portfolio_id = :p
        ),
        tot AS (SELECT NULLIF(SUM(market_value), 0) AS total FROM v)
        SELECT COALESCE(t.asset_class, v.asset_class)                            AS asset_class,
               round(COALESCE(v.market_value, 0), 2)                             AS market_value,
               round(100 * COALESCE(v.market_value, 0) / tot.total, 2)           AS actual_pct,
               t.target_pct                                                      AS target_pct,
               round(100 * COALESCE(v.market_value, 0) / tot.total - COALESCE(t.target_pct, 0), 2) AS drift_pct
        FROM t
        FULL OUTER JOIN v ON v.asset_class = t.asset_class
        CROSS JOIN tot
        ORDER BY COALESCE(t.target_pct, 0) DESC, asset_class
        """
    ), {"p": portfolio_id}))


def portfolio_value_series(conn: Connection, portfolio_id: int) -> pd.Series:
    """Daily portfolio value (sum of quantity * close), indexed by date.

    Only dates on which EVERY quantified holding has a price are kept.
    A date with a missing price would otherwise understate the value and
    show up as a fake one-day crash in the return series.
    """
    rows = conn.execute(text(
        """
        WITH h AS (
            SELECT asset_id, quantity FROM portfolio_holdings
            WHERE portfolio_id = :p AND quantity IS NOT NULL
        )
        SELECT mp.price_date, SUM(h.quantity * mp.close) AS value
        FROM h JOIN market_prices mp ON mp.asset_id = h.asset_id
        GROUP BY mp.price_date
        HAVING COUNT(*) = (SELECT COUNT(*) FROM h)
        ORDER BY mp.price_date
        """
    ), {"p": portfolio_id}).fetchall()
    return pd.Series(
        [float(v) for _, v in rows],
        index=pd.to_datetime([d for d, _ in rows]),
        dtype="float64",
        name="value",
    )


def ticker_exists(conn: Connection, ticker: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM assets WHERE ticker = :t"), {"t": ticker}
    ).first() is not None


def price_history(
    conn: Connection, ticker: str, start: date | None, end: date | None, limit: int
) -> list[dict]:
    """Most recent `limit` rows in [start, end], returned oldest first."""
    return _rows(conn.execute(text(
        """
        SELECT price_date, open, high, low, close, volume FROM (
            SELECT mp.price_date, mp.open, mp.high, mp.low, mp.close, mp.volume
            FROM market_prices mp
            JOIN assets a ON a.asset_id = mp.asset_id
            WHERE a.ticker = :t
              AND (CAST(:start AS DATE) IS NULL OR mp.price_date >= CAST(:start AS DATE))
              AND (CAST(:end   AS DATE) IS NULL OR mp.price_date <= CAST(:end   AS DATE))
            ORDER BY mp.price_date DESC
            LIMIT :limit
        ) recent
        ORDER BY price_date
        """
    ), {"t": ticker, "start": start, "end": end, "limit": limit}))
