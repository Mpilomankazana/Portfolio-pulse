# PortfolioPulse

WeThinkCode_ Data Engineering elective project, aligned with 27four Investment
Managers' portfolio analytics needs — multi-manager fund architectures, asset
allocation tracking, and market time-series ingestion.

## Architecture

```
[ Financial Market APIs / CSVs ]
              │
              ▼
[ Ingestion Engine (Python/Pandas) ]
              │
              ▼
[ Data Cleaning & Transformation (ETL) ]
              │
              ▼
[ PostgreSQL Database ] ◄── [ Automated Pipeline Orchestrator ]
   (Portfolio Schemas & Analytics)
```

### Schema

- `managers` — Manager ID, Firm Name, Strategy Type
- `portfolios` — Portfolio ID, Manager ID, Benchmark, Allocation %
- `assets` — Asset ID, Ticker, Asset Class (Equities, Fixed Income, Cash)
- `market_prices` — Asset ID, Date, Open, High, Low, Close, Volume (time-series)
- `portfolio_holdings` — links portfolios to constituent assets with weights

See [`sql/schema.sql`](sql/schema.sql) for full DDL with indexing.

## Tech Stack

| Component        | Technology                     |
|-------------------|--------------------------------|
| Language          | Python 3.11                    |
| Database          | PostgreSQL 16                  |
| ETL Libraries     | Pandas, SQLAlchemy, PyTest     |
| Containerization  | Docker / Docker Compose        |

## Setup

```bash
cp .env.example .env
docker compose up -d postgres    # spins up Postgres and applies sql/schema.sql
pip install -r requirements.txt
pytest                           # run unit tests
python -m src.orchestration.run_pipeline
```

## Roadmap

| Phase | Dates (2026) | Objective |
|---|---|---|
| 1. Ingestion & Schema Design | 26 Sep – 2 Oct | PostgreSQL schema for managers, portfolios, assets, market_prices |
| 2. Core ETL Pipeline Engine | 3 Oct – 9 Oct | Extract/Transform/Load modules with TDD (pytest) |
| 3. Automation & Orchestration | 10 Oct – 16 Oct | Scheduled daily runs, data quality checks, demo video |
| 4. Documentation & Submission | 17 Oct – 30 Oct | README/ERD finalization, 27four portfolio packaging, form submission |

## Portfolio SQL Analytics Examples

_To be added in Phase 4 — e.g. top-performing asset managers by quarter,
asset allocation breakdown._

## Demo

_YouTube demo link to be added in Phase 3._

## Verification Code

_3P verification code to be committed here after WeThinkCode_ form submission
(due 30 October 2026)._
