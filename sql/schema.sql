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
-- Phase 4 schema additions — required by src/analytics/sector_performance.py
-- and src/transform/clean.py's calculate_unrealized_gain_loss /
-- calculate_portfolio_allocation_drift.
-- =============================================================================

-- Sector classification per asset. Nullable rather than NOT NULL: an
-- unclassified asset is treated as a normal, expected state, not an
-- error to block loading on — calculate_sector_exposure
-- (src/analytics/sector_performance.py) already surfaces a NULL sector
-- as an explicit "Unclassified" bucket rather than dropping the asset,
-- so the schema allows that state instead of forcing every asset to be
-- classified up front.
ALTER TABLE assets ADD COLUMN IF NOT EXISTS sector VARCHAR(50)
    CHECK (sector IN ('Consumer Electronics', 'Energy', 'Entertainment',
                       'Financials', 'Healthcare', 'Technology'));

-- Dividend payments, feeding calculate_sector_dividends_vs_gains. sector
-- is intentionally NOT duplicated onto this table — callers join to
-- assets.sector, the same way calculate_sector_dividends_vs_gains's
-- other input (holdings_with_gains_df) is expected to already carry
-- sector from a join done upstream (see sector_performance.py's module
-- docstring).
CREATE TABLE IF NOT EXISTS dividends (
    dividend_id     SERIAL PRIMARY KEY,
    asset_id        INTEGER NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    dividend_amount NUMERIC(18,6) NOT NULL CHECK (dividend_amount >= 0),
    payment_date    DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dividends_asset_date
    ON dividends (asset_id, payment_date DESC);

-- quantity + cost_basis, required by calculate_unrealized_gain_loss
-- (src/transform/clean.py), which computes
-- (current_price - cost_basis) * quantity per holding.
--
-- weight_pct stays as its own independently stored column rather than
-- becoming derived from quantity * current_price / portfolio total:
-- deriving it would need a live price join everywhere weight_pct is
-- read today, which is a larger refactor than this schema addition
-- covers. The trade-off is that weight_pct and quantity/cost_basis can
-- drift out of sync if one is updated without the other — anything
-- that writes to portfolio_holdings should keep them consistent.
ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS quantity NUMERIC(18,6);
ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS cost_basis NUMERIC(18,6);

-- Target asset-class allocation per portfolio, feeding
-- calculate_portfolio_allocation_drift (src/transform/clean.py), which
-- expects a target_allocation_df with exactly these three columns.
CREATE TABLE IF NOT EXISTS portfolio_targets (
    portfolio_id  INTEGER NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    asset_class   VARCHAR(50) NOT NULL,
    target_pct    NUMERIC(5,2) NOT NULL CHECK (target_pct >= 0 AND target_pct <= 100),
    PRIMARY KEY (portfolio_id, asset_class)
);