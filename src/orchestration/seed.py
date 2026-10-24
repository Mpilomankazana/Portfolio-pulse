"""Seed reference data so the pipeline has assets to load prices against.

run_pipeline maps ticker -> asset_id from the `assets` table and skips any
ticker it can't map, so a fresh database loads nothing until this has run.

Usage:
    python -m src.orchestration.seed

Idempotent: safe to run repeatedly. Assets, holdings and targets use their
natural keys; managers and portfolios (which only have serial IDs) are
matched on firm_name / manager so reruns never duplicate them. All data is
synthetic demo data.
"""
import logging

from sqlalchemy import text

# Importing config first: loads .env, validates DATABASE_URL, configures logging.
from src.orchestration import config  # noqa: F401
from src.db import engine

logger = logging.getLogger(__name__)

# (ticker, asset_class, sector). Sector is NULL for non-equity assets.
ASSETS = [
    ("AAPL", "Equities", "Consumer Electronics"),
    ("MSFT", "Equities", "Technology"),
    ("XOM", "Equities", "Energy"),
    ("DIS", "Equities", "Entertainment"),
    ("JPM", "Equities", "Financials"),
    ("JNJ", "Equities", "Healthcare"),
    ("AGG", "Fixed Income", None),
    ("BIL", "Cash", None),
]

# (firm_name, strategy_type, benchmark, allocation_pct)
MANAGERS = [
    ("Kopano Capital", "Growth Equity", "S&P 500", 50.00),
    ("Baobab Asset Management", "Balanced", "60/40 Blend", 50.00),
]

# firm_name -> [(ticker, weight_pct, quantity, cost_basis)]. Weights sum to 100.
HOLDINGS = {
    "Kopano Capital": [
        ("AAPL", 30.00, 400, 205.00),
        ("MSFT", 30.00, 200, 400.00),
        ("JPM", 20.00, 350, 190.00),
        ("DIS", 15.00, 900, 92.00),
        ("BIL", 5.00, 500, 91.40),
    ],
    "Baobab Asset Management": [
        ("XOM", 20.00, 600, 108.00),
        ("JNJ", 20.00, 450, 155.00),
        ("AAPL", 10.00, 150, 210.00),
        ("AGG", 40.00, 1500, 97.50),
        ("BIL", 10.00, 1000, 91.40),
    ],
}

# firm_name -> {asset_class: target_pct}. Each sums to 100.
TARGETS = {
    "Kopano Capital": {"Equities": 90.00, "Fixed Income": 5.00, "Cash": 5.00},
    "Baobab Asset Management": {"Equities": 50.00, "Fixed Income": 40.00, "Cash": 10.00},
}

# (ticker, dividend_amount, payment_date)
DIVIDENDS = [
    ("AAPL", 0.25, "2026-08-14"),
    ("MSFT", 0.83, "2026-09-11"),
    ("XOM", 0.99, "2026-09-10"),
    ("JPM", 1.25, "2026-07-31"),
    ("JNJ", 1.30, "2026-09-09"),
    ("AGG", 0.30, "2026-10-01"),
]


def seed() -> None:
    with engine.begin() as conn:  # single transaction: all or nothing
        # Assets: natural key is ticker.
        for ticker, asset_class, sector in ASSETS:
            conn.execute(
                text(
                    """
                    INSERT INTO assets (ticker, asset_class, sector)
                    VALUES (:ticker, :asset_class, :sector)
                    ON CONFLICT (ticker) DO UPDATE SET
                        asset_class = EXCLUDED.asset_class,
                        sector = EXCLUDED.sector
                    """
                ),
                {"ticker": ticker, "asset_class": asset_class, "sector": sector},
            )

        # Managers + portfolios: no unique key on firm_name, so look up first.
        portfolio_ids: dict[str, int] = {}
        for firm, strategy, benchmark, allocation in MANAGERS:
            manager_id = conn.execute(
                text("SELECT manager_id FROM managers WHERE firm_name = :firm"),
                {"firm": firm},
            ).scalar()
            if manager_id is None:
                manager_id = conn.execute(
                    text(
                        "INSERT INTO managers (firm_name, strategy_type) "
                        "VALUES (:firm, :strategy) RETURNING manager_id"
                    ),
                    {"firm": firm, "strategy": strategy},
                ).scalar_one()

            portfolio_id = conn.execute(
                text("SELECT portfolio_id FROM portfolios WHERE manager_id = :m"),
                {"m": manager_id},
            ).scalar()
            if portfolio_id is None:
                portfolio_id = conn.execute(
                    text(
                        "INSERT INTO portfolios (manager_id, benchmark, allocation_pct) "
                        "VALUES (:m, :benchmark, :alloc) RETURNING portfolio_id"
                    ),
                    {"m": manager_id, "benchmark": benchmark, "alloc": allocation},
                ).scalar_one()
            portfolio_ids[firm] = portfolio_id

        asset_ids = {
            ticker: asset_id
            for asset_id, ticker in conn.execute(text("SELECT asset_id, ticker FROM assets"))
        }

        # Holdings: natural key (portfolio_id, asset_id).
        for firm, rows in HOLDINGS.items():
            for ticker, weight, quantity, cost_basis in rows:
                conn.execute(
                    text(
                        """
                        INSERT INTO portfolio_holdings
                            (portfolio_id, asset_id, weight_pct, quantity, cost_basis)
                        VALUES (:p, :a, :w, :q, :c)
                        ON CONFLICT (portfolio_id, asset_id) DO UPDATE SET
                            weight_pct = EXCLUDED.weight_pct,
                            quantity = EXCLUDED.quantity,
                            cost_basis = EXCLUDED.cost_basis
                        """
                    ),
                    {"p": portfolio_ids[firm], "a": asset_ids[ticker], "w": weight,
                     "q": quantity, "c": cost_basis},
                )

        # Targets: natural key (portfolio_id, asset_class).
        for firm, targets in TARGETS.items():
            for asset_class, target_pct in targets.items():
                conn.execute(
                    text(
                        """
                        INSERT INTO portfolio_targets (portfolio_id, asset_class, target_pct)
                        VALUES (:p, :ac, :t)
                        ON CONFLICT (portfolio_id, asset_class) DO UPDATE SET
                            target_pct = EXCLUDED.target_pct
                        """
                    ),
                    {"p": portfolio_ids[firm], "ac": asset_class, "t": target_pct},
                )

        # Dividends: serial PK only, so skip a row that already exists.
        for ticker, amount, payment_date in DIVIDENDS:
            conn.execute(
                text(
                    """
                    INSERT INTO dividends (asset_id, dividend_amount, payment_date)
                    SELECT :a, :amt, CAST(:d AS DATE)
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dividends
                        WHERE asset_id = :a AND payment_date = CAST(:d AS DATE)
                    )
                    """
                ),
                {"a": asset_ids[ticker], "amt": amount, "d": payment_date},
            )

    logger.info(
        "Seeded %d assets, %d managers, %d holdings, %d dividends",
        len(ASSETS),
        len(MANAGERS),
        sum(len(v) for v in HOLDINGS.values()),
        len(DIVIDENDS),
    )


if __name__ == "__main__":
    seed()