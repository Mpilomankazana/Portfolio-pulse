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
- `assets`: Asset ID, Ticker, Asset Class (Equities, Fixed Income, Cash)
- `market_prices`: Asset ID, Date, Open, High, Low, Close, Volume (time-series)
- `portfolio_holdings`: links portfolios to constituent assets with weights

See `sql/schema.sql` for full DDL with indexing.

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
pip install -r requirements.txt
pytest -m "not integration"      # run the unit suite (no DB required)
python -m src.orchestration.run_pipeline
```

### Scheduled runs

The pipeline runs on a cron schedule via APScheduler (`src/orchestration/scheduler.py`).
Defaults: 18:00 weekdays, `Africa/Johannesburg` time. Override with `PIPELINE_SCHEDULE` and `SCHEDULER_TIMEZONE` in `.env`.

```
python -m src.orchestration.scheduler --run-now   # run once now, then on schedule
docker compose up -d scheduler                    # or run it as a container
```

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

To be added in Phase 4, e.g. top-performing asset managers by quarter, asset allocation breakdown.

## Demo

Demo link to be added in Phase 3.

## Verification Code

Verification code to be committed here after final submission (due 30 October 2026).