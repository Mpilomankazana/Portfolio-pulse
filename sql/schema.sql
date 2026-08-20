-- Financial Asset Data Pipeline & Multi-Manager Portfolio ETL Platform
-- Phase 1: Core schema — managers, portfolios, assets, market_prices

CREATE TABLE IF NOT EXISTS managers (
    manager_id      SERIAL PRIMARY KEY,
    firm_name       VARCHAR(255) NOT NULL,
    strategy_type   VARCHAR(100) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id    SERIAL PRIMARY KEY,
    manager_id      INTEGER NOT NULL REFERENCES managers(manager_id) ON DELETE CASCADE,
    benchmark       VARCHAR(100),
    allocation_pct  NUMERIC(5,2) NOT NULL CHECK (allocation_pct >= 0 AND allocation_pct <= 100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portfolios_manager_id ON portfolios(manager_id);

CREATE TABLE IF NOT EXISTS assets (
    asset_id        SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL UNIQUE,
    asset_class     VARCHAR(50) NOT NULL CHECK (asset_class IN ('Equities', 'Fixed Income', 'Cash')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Time-series market prices, indexed for range queries per asset
CREATE TABLE IF NOT EXISTS market_prices (
    asset_id        INTEGER NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    price_date      DATE NOT NULL,
    open            NUMERIC(18,6),
    high            NUMERIC(18,6),
    low             NUMERIC(18,6),
    close           NUMERIC(18,6),
    volume          BIGINT,
    PRIMARY KEY (asset_id, price_date)
);

CREATE INDEX IF NOT EXISTS idx_market_prices_asset_date
    ON market_prices (asset_id, price_date DESC);

-- Optional: link portfolios to constituent assets for weighted-return calcs later
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    asset_id        INTEGER NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    weight_pct      NUMERIC(5,2) NOT NULL CHECK (weight_pct >= 0 AND weight_pct <= 100),
    PRIMARY KEY (portfolio_id, asset_id)
);

-- =============================================================================
-- TODO: Phase 4 schema additions — required by src/analytics/sector_performance.py
-- and src/transform/clean.py's calculate_unrealized_gain_loss /
-- calculate_portfolio_allocation_drift. Not yet applied — draft DDL below.
-- =============================================================================

-- TODO: add a `sector` column to the existing `assets` table (ALTER TABLE,
-- since assets already exists above — don't recreate it):
--   ALTER TABLE assets ADD COLUMN sector VARCHAR(50)
--       CHECK (sector IN ('Consumer Electronics', 'Energy', 'Entertainment',
--                          'Financials', 'Healthcare', 'Technology'));
-- Decide whether sector should be NOT NULL (forces every asset to be
-- classified) or nullable with an "Unclassified" fallback handled in
-- src/analytics/sector_performance.py's calculate_sector_exposure.

-- TODO: new `dividends` table, feeding calculate_sector_dividends_vs_gains:
--   CREATE TABLE dividends (
--       dividend_id     SERIAL PRIMARY KEY,
--       asset_id        INTEGER NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
--       dividend_amount NUMERIC(18,6) NOT NULL CHECK (dividend_amount >= 0),
--       payment_date    DATE NOT NULL
--   );
--   CREATE INDEX idx_dividends_asset_date ON dividends (asset_id, payment_date DESC);

-- TODO: portfolio_holdings needs quantity + cost_basis to support
-- calculate_unrealized_gain_loss (currently only has weight_pct, which
-- isn't enough to compute a dollar gain/loss):
--   ALTER TABLE portfolio_holdings ADD COLUMN quantity NUMERIC(18,6);
--   ALTER TABLE portfolio_holdings ADD COLUMN cost_basis NUMERIC(18,6);
-- Decide whether weight_pct becomes derived (computed from quantity *
-- current price / portfolio total) rather than a separately stored value,
-- to avoid the two drifting out of sync.

-- TODO: target allocation table, feeding
-- calculate_portfolio_allocation_drift (currently that function expects a
-- target_allocation_df with no backing table yet):
--   CREATE TABLE portfolio_targets (
--       portfolio_id  INTEGER NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
--       asset_class   VARCHAR(50) NOT NULL,
--       target_pct    NUMERIC(5,2) NOT NULL CHECK (target_pct >= 0 AND target_pct <= 100),
--       PRIMARY KEY (portfolio_id, asset_class)
--   );
