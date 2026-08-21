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
pytest                           # run unit tests
python -m src.orchestration.run_pipeline
```

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
