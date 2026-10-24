-- PortfolioPulse: example analytics queries.
--
-- Run against a seeded database (see README "Setup"):
--   psql "$DATABASE_URL" -f sql/analytics_examples.sql
--
-- Portfolio values below use constant quantities from portfolio_holdings
-- (quantity * close), so returns reflect price moves only, not trading.
-- Each query starts with a "-- N." header; tests/integration/test_analytics_sql.py
-- splits on those headers, so keep that format.

-- 1. Manager performance by quarter (constant-quantity portfolio return).
-- Start/end price = first/last close the asset has within the quarter.
WITH q AS (
    SELECT asset_id,
           date_trunc('quarter', price_date)::date AS quarter,
           (array_agg(close ORDER BY price_date ASC))[1]  AS start_close,
           (array_agg(close ORDER BY price_date DESC))[1] AS end_close
    FROM market_prices
    GROUP BY asset_id, date_trunc('quarter', price_date)
)
SELECT to_char(q.quarter, 'YYYY"-Q"Q')                          AS quarter,
       m.firm_name,
       round(SUM(h.quantity * q.start_close), 2)                AS start_value,
       round(SUM(h.quantity * q.end_close), 2)                  AS end_value,
       round((SUM(h.quantity * q.end_close)
            / SUM(h.quantity * q.start_close) - 1) * 100, 2)    AS return_pct,
       RANK() OVER (PARTITION BY q.quarter
                    ORDER BY SUM(h.quantity * q.end_close)
                           / SUM(h.quantity * q.start_close) DESC) AS rank
FROM portfolio_holdings h
JOIN portfolios p ON p.portfolio_id = h.portfolio_id
JOIN managers   m ON m.manager_id   = p.manager_id
JOIN q            ON q.asset_id     = h.asset_id
GROUP BY q.quarter, m.firm_name
ORDER BY q.quarter, rank;

-- 2. Asset allocation by asset class at latest prices, with drift vs target.
-- Starts from portfolio_targets so a target class with no holdings still
-- appears (as 0% actual) instead of silently disappearing.
WITH latest AS (
    SELECT DISTINCT ON (asset_id) asset_id, close
    FROM market_prices
    ORDER BY asset_id, price_date DESC
),
values_by_class AS (
    SELECT h.portfolio_id, a.asset_class,
           SUM(h.quantity * l.close) AS market_value
    FROM portfolio_holdings h
    JOIN assets a ON a.asset_id = h.asset_id
    JOIN latest l ON l.asset_id = h.asset_id
    GROUP BY h.portfolio_id, a.asset_class
),
totals AS (
    SELECT portfolio_id, SUM(market_value) AS total FROM values_by_class GROUP BY portfolio_id
)
SELECT m.firm_name,
       t.asset_class,
       round(COALESCE(v.market_value, 0), 2)                           AS market_value,
       round(100 * COALESCE(v.market_value, 0) / tot.total, 2)         AS actual_pct,
       t.target_pct,
       round(100 * COALESCE(v.market_value, 0) / tot.total - t.target_pct, 2) AS drift_pct
FROM portfolio_targets t
JOIN portfolios p ON p.portfolio_id = t.portfolio_id
JOIN managers   m ON m.manager_id   = p.manager_id
JOIN totals   tot ON tot.portfolio_id = t.portfolio_id
LEFT JOIN values_by_class v
       ON v.portfolio_id = t.portfolio_id AND v.asset_class = t.asset_class
ORDER BY m.firm_name, t.target_pct DESC;

-- 3. Unrealized gain/loss per holding, using each asset's latest close.
WITH latest AS (
    SELECT DISTINCT ON (asset_id) asset_id, close
    FROM market_prices
    ORDER BY asset_id, price_date DESC
)
SELECT m.firm_name,
       a.ticker,
       trim_scale(h.quantity)                                     AS quantity,
       round(h.cost_basis, 2)                                     AS cost_basis,
       round(l.close, 2)                                          AS latest_close,
       round((l.close - h.cost_basis) * h.quantity, 2)            AS unrealized_gl,
       round((l.close / h.cost_basis - 1) * 100, 2)               AS gl_pct
FROM portfolio_holdings h
JOIN portfolios p ON p.portfolio_id = h.portfolio_id
JOIN managers   m ON m.manager_id   = p.manager_id
JOIN assets     a ON a.asset_id     = h.asset_id
JOIN latest     l ON l.asset_id     = h.asset_id
ORDER BY unrealized_gl DESC
LIMIT 5;

-- 4. Sector exposure at latest prices, with dividends received per sector.
WITH latest AS (
    SELECT DISTINCT ON (asset_id) asset_id, close
    FROM market_prices
    ORDER BY asset_id, price_date DESC
),
exposure AS (
    SELECT COALESCE(a.sector, 'Unclassified') AS sector,
           SUM(h.quantity * l.close)          AS market_value
    FROM portfolio_holdings h
    JOIN assets a ON a.asset_id = h.asset_id
    JOIN latest l ON l.asset_id = h.asset_id
    GROUP BY COALESCE(a.sector, 'Unclassified')
),
divs AS (
    SELECT COALESCE(a.sector, 'Unclassified') AS sector,
           SUM(d.dividend_amount * h.quantity) AS dividends
    FROM dividends d
    JOIN assets a ON a.asset_id = d.asset_id
    JOIN portfolio_holdings h ON h.asset_id = d.asset_id
    GROUP BY COALESCE(a.sector, 'Unclassified')
)
SELECT e.sector,
       round(e.market_value, 2)                                    AS market_value,
       round(100 * e.market_value / SUM(e.market_value) OVER (), 2) AS pct_of_total,
       round(COALESCE(d.dividends, 0), 2)                          AS dividends_received
FROM exposure e
LEFT JOIN divs d USING (sector)
ORDER BY e.market_value DESC;