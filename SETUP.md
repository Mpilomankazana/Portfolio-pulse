# PortfolioPulse setup guide

This guide takes you from a fresh clone to a working pipeline, database, REST API,
scheduler and test suite. Commands are shown for **Windows PowerShell** first, with
macOS/Linux equivalents where they differ.

If you only want it running, do sections 1 to 6. Everything after that is optional.

## 1. What you need

| Tool | Version | Why |
|---|---|---|
| Python | 3.11 or newer | Runs the pipeline, API and tests. The Docker image uses 3.11; 3.13 and 3.14 also work. |
| Git | any recent | Clone the repository. |
| Docker Desktop | any recent, running | Runs PostgreSQL 16. You can skip Docker only if you already run your own PostgreSQL 16 (see section 12). |
| Git Bash or WSL | optional | Only for `scripts/verify_clean_clone.sh` (section 11). |

Check them:

```
python --version
git --version
docker --version
docker compose version
```

## 2. Get the code

```
git clone https://github.com/Mpilomankazana/Portfolio-pulse.git
cd Portfolio-pulse
```

## 3. Create a Python environment and install dependencies

```
python -m venv .venv
```

Activate it:

| System | Command |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

If PowerShell says running scripts is disabled, run this once in the same window and activate again:

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Install everything (runtime and test dependencies):

```
python -m pip install -r requirements-dev.txt
```

> Always run Python tools as `python -m ...` (for example `python -m pytest`). On Windows the
> `pytest` and `uvicorn` commands are often not on PATH, but `python -m` always works.

## 4. Configure the environment

```
Copy-Item .env.example .env        # Windows PowerShell
cp .env.example .env               # macOS / Linux
```

The defaults work as they are. You only need to edit `.env` for the optional features below.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `de27four`, `de27four_pw`, `portfolio_analytics` | Database credentials the Docker container is created with |
| `DATABASE_URL` | `postgresql://de27four:de27four_pw@localhost:5432/portfolio_analytics` | Where Python connects when you run it on your machine |
| `DATA_SOURCE` | `csv` | `csv` reads `CSV_SOURCES`; `api` calls Alpha Vantage (section 9) |
| `CSV_SOURCES` | `data/sample_prices.csv` | Comma-separated CSV files for the `csv` source |
| `MARKET_API_KEY` | empty | Alpha Vantage key, only needed for `DATA_SOURCE=api` |
| `API_TICKERS`, `API_LOOKBACK_DAYS`, `API_PAUSE_SECONDS` | empty, `30`, `12` | Which tickers, how many days back, and the pause between tickers for the API source |
| `PIPELINE_SCHEDULE`, `SCHEDULER_TIMEZONE` | `0 18 * * 1-5`, `Africa/Johannesburg` | When the scheduler runs (18:00 on weekdays) |
| `LAKE_ENABLED`, `LAKE_DIR` | `true`, `./lake` | Parquet data lake written next to the database load |
| `API_KEY` | empty | If set, the REST API requires an `X-API-Key` header (except `/health`) |

`.env` is git-ignored. Never commit it.

## 5. Start the database

Make sure Docker Desktop is running, then:

```
docker compose up -d postgres
docker compose ps
```

Wait until `de27four_postgres` shows `healthy` (about 10 seconds the first time). On the first start
PostgreSQL creates the tables from `sql/schema.sql` automatically.

## 6. Load reference data and run the pipeline

Seed the managers, portfolios, assets, holdings, targets and dividends (safe to repeat):

```
python -m src.orchestration.seed
```

You should see `Seeded 8 assets, 2 managers, 10 holdings, 6 dividends`.

Run the pipeline once (extract, clean, validate, flag outliers, write the data lake, load into PostgreSQL):

```
python -m src.orchestration.run_pipeline
```

You should see `Upserted 480 rows into market_prices` and a final line starting
`Run summary: status=success`. Run it a second time: the row count stays at 480, because the load is an upsert.

Check the data:

```
docker compose exec postgres psql -U de27four -d portfolio_analytics -c "SELECT count(*) FROM market_prices;"
```

The pipeline's exit code is 0 on success, and 1 if nothing at all was loaded.
In PowerShell check it with `$LASTEXITCODE`; in bash with `echo $?`.

## 7. See the analytics

The four example queries (manager ranking, allocation drift, unrealised gains, sector exposure):

```
Get-Content sql/analytics_examples.sql | docker compose exec -T postgres psql -U de27four -d portfolio_analytics     # PowerShell
docker compose exec -T postgres psql -U de27four -d portfolio_analytics < sql/analytics_examples.sql                 # bash
```

PowerShell does not support the `<` redirect, which is why it uses `Get-Content` and a pipe.

## 8. Run the REST API

```
python -m uvicorn src.api.main:app
```

Open <http://localhost:8000/docs> for interactive documentation. Try these in a second window:

```
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/managers/rankings
curl.exe "http://localhost:8000/portfolios/1/risk?confidence=0.95"
```

(In PowerShell use `curl.exe`; plain `curl` is an alias for a different command.)

If you set `API_KEY` in `.env`, add `-H "X-API-Key: <your key>"` to every request except `/health`.

To run the API in Docker instead (published on `127.0.0.1:8000` only):

```
docker compose up -d api
```

## 9. Use live market data (optional)

1. Get a free key from <https://www.alphavantage.co/support/#api-key>.
2. Edit `.env`:

   ```
   DATA_SOURCE=api
   MARKET_API_KEY=your-key-here
   API_TICKERS=AAPL,MSFT
   API_LOOKBACK_DAYS=30
   API_PAUSE_SECONDS=12
   ```

3. Run `python -m src.orchestration.run_pipeline`.

Only tickers that exist in the `assets` table are loaded. The seeded ones are
`AAPL, MSFT, XOM, DIS, JPM, JNJ, AGG, BIL`. The free tier allows about 5 requests per minute and a small
number per day, so keep the ticker list short. If Alpha Vantage answers with a quota or rate-limit
message, the log shows it, the run is marked `no_data`, and the exit code is 1.

Set `DATA_SOURCE=csv` again to go back to the sample data.

## 10. Run the scheduler

Run the pipeline once now and then every weekday at 18:00 (Johannesburg time by default):

```
python -m src.orchestration.scheduler --run-now
```

Stop it with `Ctrl+C`. To run it in Docker (it also waits for the seed step):

```
docker compose up -d scheduler
docker compose logs -f scheduler
```

A run that loads nothing is logged as `Scheduled run FAILED`; a run where some tickers failed logs a warning.

## 11. Run the tests

Unit tests (no database needed):

```
python -m pytest -m "not integration"
```

Integration tests (need the separate test database, which is emptied at the start of each run):

```
docker compose up -d postgres_test
$env:TEST_DATABASE_URL = "postgresql://de27four_test:de27four_test_pw@localhost:5433/portfolio_analytics_test"    # PowerShell
export TEST_DATABASE_URL=postgresql://de27four_test:de27four_test_pw@localhost:5433/portfolio_analytics_test      # bash
python -m pytest -m integration
```

Everything together: `python -m pytest`.

The integration tests refuse to run unless the database name ends in `_test`, so they can never wipe your dev database.

Full clean-clone check (deletes the dev database volume, rebuilds the containers, seeds, runs the pipeline twice,
runs the SQL, starts the scheduler and API, checks the lake). Needs Git Bash or WSL on Windows:

```
bash scripts/verify_clean_clone.sh
```

## 12. Without Docker

If you already have PostgreSQL 16 installed, create the role and database that `.env` expects, apply the schema,
and continue from section 6:

```
psql -U postgres -c "CREATE USER de27four WITH PASSWORD 'de27four_pw';"
psql -U postgres -c "CREATE DATABASE portfolio_analytics OWNER de27four;"
psql -U de27four -d portfolio_analytics -f sql/schema.sql
```

For the integration tests create a second database named `portfolio_analytics_test` the same way and point
`TEST_DATABASE_URL` at it.

## 13. Stop and reset

| Goal | Command |
|---|---|
| Stop everything, keep the data | `docker compose down` |
| Stop everything and delete the database and lake | `docker compose down -v` |
| Re-run the pipeline in Docker | `docker compose run --rm app` |
| Regenerate the sample CSV | `python scripts/generate_sample_prices.py` |

## 14. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `pytest` / `uvicorn` is not recognized | The Python scripts folder is not on PATH. Use `python -m pytest` and `python -m uvicorn`. |
| `failed to connect to the docker API` | Docker Desktop is not running. Start it and retry. |
| `port is already allocated` on 5432 or 5433 | Another PostgreSQL is using that port. Stop it, or change the left-hand number in the `ports:` line of `docker-compose.yml` and in `DATABASE_URL`. |
| `relation "assets" does not exist` | The schema is only applied the first time a database volume is created. Run `docker compose down -v`, then `docker compose up -d postgres`. |
| Pipeline says tickers have no matching asset_id | Run the seed step first: `python -m src.orchestration.seed`. |
| `Run summary: status=no_data` and exit code 1 | Nothing was loaded. With the API source, read the warning above it (quota, rate limit or bad key). With CSV, check the `CSV_SOURCES` paths. |
| `TEST_DATABASE_URL is not set` | Set it as shown in section 11. |
| `Refusing to run integration tests against database ...` | The database name must end in `_test`. Use the `postgres_test` service. |
| `DATA_SOURCE=api needs MARKET_API_KEY` | Set `MARKET_API_KEY` and `API_TICKERS` in `.env`, or set `DATA_SOURCE=csv`. |
| API returns `401` | `API_KEY` is set. Send the `X-API-Key` header, or empty `API_KEY` in `.env` and restart the API. |
| Git shows every file as modified | Line endings. The repository normalises them with `.gitattributes`; run `git add --renormalize .` once. |

## 15. Project layout

```
src/extract/        CSV and Alpha Vantage extractors
src/transform/      cleaning, validation, returns, outlier flags
src/load/           PostgreSQL upsert and the Parquet data lake
src/analytics/      valuation, drawdown, rankings, sectors, VaR/CVaR, benchmark, Sharpe/Sortino
src/api/            read-only REST API (FastAPI)
src/orchestration/  config, seed, pipeline entry point, scheduler
sql/                schema.sql and the example analytics queries
docs/               ERD (erd.mmd) and design notes
tests/              unit tests; tests/integration needs a real PostgreSQL
scripts/            sample data generator and the clean-clone check
```

See `docs/design_notes.md` for the design decisions and what is deliberately not implemented.
