# PortfolioPulse

An automated multi-manager ETL and portfolio analytics engine: multi-manager fund architectures, asset allocation tracking, and market time-series ingestion.

## Architecture

```
[ Financial Market APIs / CSVs ]
              |
              v
[ Ingestion Engine (Python/Pandas) ]
              |
              v
[ Data Cleaning & Transformation (ETL) ]
              |
              v
[ PostgreSQL Database ] <-- [ Automated Pipeline Orchestrator ]
   (Portfolio Schemas & Analytics)
```

## Schema

- `managers`: Manager ID, Firm Name, Strategy Type
- `portfolios`: Portfolio ID, Manager ID, Benchmark, Allocation %
- `assets`: Asset ID, Ticker, Asset Class (Equities, Fixed Income, Cash), Sector (nullable)
- `market_prices`: Asset ID, Date, Open, High, Low, Close, Volume (time-series)
- `portfolio_holdings`: links portfolios to constituent assets with weight, quantity and cost basis
- `portfolio_targets`: target allocation % per asset class per portfolio
- `dividends`: dividend payments per asset

See `sql/schema.sql` for full DDL with indexing.

### Entity-relationship diagram

```mermaid
erDiagram
    managers ||--o{ portfolios : "runs"
    portfolios ||--o{ portfolio_holdings : "holds"
    assets ||--o{ portfolio_holdings : "held as"
    assets ||--o{ market_prices : "priced by"
    assets ||--o{ dividends : "pays"
    portfolios ||--o{ portfolio_targets : "targets"

    managers {
        int manager_id PK
        varchar firm_name
        varchar strategy_type
        timestamptz created_at
    }

    portfolios {
        int portfolio_id PK
        int manager_id FK
        varchar benchmark "nullable"
        numeric allocation_pct "0-100"
        timestamptz created_at
    }

    assets {
        int asset_id PK
        varchar ticker UK
        varchar asset_class "Equities, Fixed Income, Cash"
        varchar sector "nullable"
        timestamptz created_at
    }

    market_prices {
        int asset_id PK, FK
        date price_date PK
        numeric open
        numeric high
        numeric low
        numeric close
        bigint volume
    }

    portfolio_holdings {
        int portfolio_id PK, FK
        int asset_id PK, FK
        numeric weight_pct "0-100"
        numeric quantity "nullable"
        numeric cost_basis "nullable"
    }

    portfolio_targets {
        int portfolio_id PK, FK
        varchar asset_class PK "matches assets.asset_class by value, not FK"
        numeric target_pct "0-100"
    }

    dividends {
        int dividend_id PK
        int asset_id FK
        numeric dividend_amount
        date payment_date
    }
```

The same diagram lives in `docs/erd.mmd` for tools that take a standalone Mermaid file. Notes:

- A manager can run several portfolios; the schema allows it, the sample data uses one each.
- `portfolio_holdings` is the many-to-many link between portfolios and assets.
- `portfolio_targets.asset_class` matches `assets.asset_class` by value only. It is not a foreign key, because targets are per class, not per asset.
- `weight_pct` is stored independently of `quantity` and `cost_basis`, so writers must keep them consistent.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| Database | PostgreSQL 16 |
| ETL Libraries | Pandas, SQLAlchemy, PyTest |
| Containerization | Docker / Docker Compose |

## Setup

```
cp .env.example .env
docker compose up -d postgres    # spins up Postgres and applies sql/schema.sql
pip install -r requirements-dev.txt
pytest -m "not integration"      # run the unit suite (no DB required)
python -m src.orchestration.seed          # first run only: managers, portfolios, assets (idempotent)
python -m src.orchestration.run_pipeline  # loads CSV_SOURCES (default: data/sample_prices.csv)
```

`data/sample_prices.csv` is synthetic demo data (8 tickers, 60 trading days). Regenerate it with `python scripts/generate_sample_prices.py`. Point the pipeline at your own files with `CSV_SOURCES=path/a.csv,path/b.csv` in `.env`.

### Scheduled runs

The pipeline runs on a cron schedule via APScheduler (`src/orchestration/scheduler.py`).
Defaults: 18:00 weekdays, `Africa/Johannesburg` time. Override with `PIPELINE_SCHEDULE` and `SCHEDULER_TIMEZONE` in `.env`.

```
python -m src.orchestration.scheduler --run-now   # run once now, then on schedule
docker compose up -d scheduler                    # or run it as a container
```

In Docker, the `seed` service runs first and `app` / `scheduler` wait for it, so a fresh `docker compose up -d scheduler` works from an empty database. Run the pipeline once with `docker compose run --rm app`.

To check a clean clone end to end (fresh volumes, seed, pipeline, rerun, analytics SQL, scheduler), run `bash scripts/verify_clean_clone.sh`. It deletes the dev database volume.

### Running integration tests

The unit suite mocks the database (see `tests/test_loader.py`,
`tests/test_extract.py`) and never needs Postgres running. A separate
integration suite under `tests/integration/` runs against a real
Postgres 16 instance instead, using a dedicated `postgres_test`
docker-compose service so it never touches dev data:

```
docker compose up -d postgres_test
export TEST_DATABASE_URL=postgresql://de27four_test:de27four_test_pw@localhost:5433/portfolio_analytics_test
pytest -m integration             # just the integration suite
pytest                            # everything, unit + integration
```

`sql/schema.sql` is applied automatically by the `pg_engine` fixture
before any integration test runs (it's idempotent, so this is safe
whether `postgres_test` is a fresh container or a reused one).

## Roadmap

| Phase | Objective |
|---|---|
| 1. Ingestion & Schema Design | PostgreSQL schema for managers, portfolios, assets, market_prices |
| 2. Core ETL Pipeline Engine | Extract/Transform/Load modules with TDD (pytest) |
| 3. Automation & Orchestration | Scheduled daily runs, data quality checks, demo video |
| 4. Documentation & Submission | README/ERD finalization, portfolio packaging, final submission |

## Portfolio SQL Analytics Examples

The queries below are in `sql/analytics_examples.sql` and run against the seeded sample data (`python -m src.orchestration.seed` then `python -m src.orchestration.run_pipeline`). Output shown is from a real run against Postgres 16; the data is synthetic, so the figures are illustrative.

```
psql "$DATABASE_URL" -f sql/analytics_examples.sql
```

### 1. Top-performing managers by quarter

Ranks managers by constant-quantity portfolio return within each calendar quarter. The sample data runs 3 Aug to 23 Oct 2026, so Q3 covers Aug-Sep and Q4 is a partial quarter (Oct only).

```sql
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
```

Result:

```
 quarter |        firm_name        | start_value | end_value | return_pct | rank 
---------+-------------------------+-------------+-----------+------------+------
 2026-Q3 | Baobab Asset Management |   412212.07 | 416807.57 |       1.11 |    1
 2026-Q3 | Kopano Capital          |   386736.81 | 383736.09 |      -0.78 |    2
 2026-Q4 | Kopano Capital          |   384561.45 | 391267.25 |       1.74 |    1
 2026-Q4 | Baobab Asset Management |   415860.09 | 420626.41 |       1.15 |    2
(4 rows)
```

### 2. Asset allocation vs target

Actual allocation by asset class at latest prices against `portfolio_targets`. Starts from the targets table, so a target class with no holdings (Kopano's 5% Fixed Income) still shows up as 0% rather than vanishing.

```sql
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
```

Result:

```
 firm_name        | asset_class  | market_value | actual_pct | target_pct | drift_pct 
-------------------------+--------------+--------------+------------+------------+-----------
 Baobab Asset Management | Equities     |    175865.91 |      41.81 |      50.00 |     -8.19
 Baobab Asset Management | Fixed Income |    151717.50 |      36.07 |      40.00 |     -3.93
 Baobab Asset Management | Cash         |     93043.00 |      22.12 |      10.00 |     12.12
 Kopano Capital          | Equities     |    344745.75 |      88.11 |      90.00 |     -1.89
 Kopano Capital          | Cash         |     46521.50 |      11.89 |       5.00 |      6.89
 Kopano Capital          | Fixed Income |         0.00 |       0.00 |       5.00 |     -5.00
(6 rows)
```

### 3. Biggest unrealized gains

Unrealized gain/loss per holding, `(latest close - cost_basis) * quantity`, top five.

```sql
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
```

Result:

```
 firm_name        | ticker | quantity | cost_basis | latest_close | unrealized_gl | gl_pct 
-------------------------+--------+----------+------------+--------------+---------------+--------
 Kopano Capital          | JPM    |      350 |     190.00 |       220.11 |      10538.43 |  15.85
 Kopano Capital          | DIS    |      900 |      92.00 |       103.37 |      10229.04 |  12.35
 Baobab Asset Management | XOM    |      600 |     108.00 |       118.73 |       6439.56 |   9.94
 Kopano Capital          | AAPL   |      400 |     205.00 |       220.96 |       6382.64 |   7.78
 Kopano Capital          | MSFT   |      200 |     400.00 |       431.48 |       6295.64 |   7.87
(5 rows)
```

### 4. Sector exposure and dividends

Market value by sector across all portfolios, plus dividends received (`dividend_amount * quantity` held). `Unclassified` is every asset with a NULL sector, i.e. the Fixed Income and Cash positions.

```sql
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
```

Result:

```
 sector        | market_value | pct_of_total | dividends_received 
----------------------+--------------+--------------+--------------------
 Unclassified         |    291282.00 |        35.88 |             450.00
 Consumer Electronics |    121526.13 |        14.97 |             137.50
 Entertainment        |     93029.04 |        11.46 |               0.00
 Technology           |     86295.64 |        10.63 |             166.00
 Financials           |     77038.43 |         9.49 |             437.50
 Healthcare           |     71482.86 |         8.80 |             585.00
 Energy               |     71239.56 |         8.77 |             594.00
(7 rows)
```

## Demo

Demo link to be added in Phase 3.

## Verification Code

Verification code to be committed here after final submission (due 30 October 2026).