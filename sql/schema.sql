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
