# Design notes

Why the project is built the way it is, and where it stops. Each section says
what exists, what is a deliberate trade-off, and what is **not** implemented.

## 1. Schema design and normalisation

The schema (see the ERD in the README) is in third normal form, with three
deliberate exceptions listed below.

| Form | How the schema meets it |
|---|---|
| 1NF | Every column holds one atomic value; every table has a primary key; no repeating groups (a manager's several portfolios are rows in `portfolios`, not a list column). |
| 2NF | The three composite-key tables have no partial dependencies. In `market_prices (asset_id, price_date)` the OHLCV values describe one asset on one day, so they depend on the whole key. The same holds for `portfolio_holdings (portfolio_id, asset_id)` and `portfolio_targets (portfolio_id, asset_class)`. |
| 3NF | No non-key column depends on another non-key column. `assets.sector` is deliberately **not** copied onto `dividends`; queries join to `assets` instead, so a sector change is made in one row. |

**Deliberate exceptions (trade-offs, not oversights):**

1. **`portfolio_holdings.weight_pct` is derivable.** It could be computed from
   `quantity * latest close / portfolio total`. It is stored because the
   original schema had it before quantities existed. The cost: it can drift out
   of sync with `quantity`, so anything that writes holdings must update both.
   The API computes values from `quantity` and never trusts `weight_pct`.
2. **`asset_class` and `sector` are `CHECK`-constrained strings, not lookup
   tables.** A fixed list of three classes and six sectors does not justify two
   extra tables and joins. If the lists grew or needed attributes, they would
   become `asset_classes` and `sectors` tables referenced by foreign key.
3. **`portfolios.benchmark` is free text** (`'S&P 500'`). Normalised, it would be
   a `benchmarks` table. Not done because no benchmark price data is loaded yet.

`portfolio_targets.asset_class` matches `assets.asset_class` by value, not by
foreign key, because a target is per class, not per asset.

## 2. ACID in practice

| Property | Where it shows up |
|---|---|
| Atomicity | `upsert_market_prices` and the seed script each run in one transaction (`engine.begin()`): a failure rolls back the whole batch, never half a load. |
| Consistency | Primary keys, foreign keys with `ON DELETE CASCADE`, and `CHECK` constraints (percentages 0-100, dividends >= 0, allowed asset classes and sectors). **Gap:** `market_prices` has no `CHECK` on its values, so the price rules (positive prices, `high >= low`) are enforced by the Python validation only; a direct SQL insert could bypass them. |
| Isolation | PostgreSQL's default `READ COMMITTED`. Two runs at once (scheduler plus a manual run) are safe because the upsert is a single `INSERT ... ON CONFLICT DO UPDATE` per row key; the last writer wins and nothing duplicates. The scheduler also uses `max_instances=1`. |
| Durability | PostgreSQL's write-ahead log, with data on the `pgdata` named volume so it survives container restarts. |

**Limit:** the data lake files are written outside the database transaction. A
run can succeed in Postgres and fail on a Parquet write, or the reverse, so
Postgres is the system of record and lake writes are best-effort (a lake
failure is logged and recorded in the run manifest, and the load continues).

## 3. CAP theorem and scaling

The project runs one PostgreSQL node, so there is no network partition between
database nodes to tolerate and CAP's trade-off never has to be made. The
reasoning for a larger deployment:

- This is financial data: serving a stale or conflicting portfolio value is
  worse than refusing to answer. The right choice under a partition is
  **consistency over availability (CP)**: synchronous replication, with writes
  blocked if a replica cannot be reached.
- Read replicas fed asynchronously would be an AP-leaning choice (fast, always
  answering, possibly stale) and suit dashboards, not valuation.

Scaling `market_prices` (the only table that grows quickly) would go in this
order, and **none of it is implemented**:

1. Native PostgreSQL range partitioning by `price_date`: old partitions can be
   archived or dropped cheaply, and recent-date queries touch less data.
2. Read replicas for the API.
3. Sharding by `asset_id` hash only at much larger scale. Single-asset queries
   would stay on one shard; portfolio queries spanning many assets would need to
   gather from several, which is the cost.

## 4. Storage formats, lake vs warehouse, ETL vs ELT

| Layer | Format | Where | Purpose |
|---|---|---|---|
| Source | CSV / REST JSON | `data/`, Alpha Vantage | What providers give us |
| Raw zone | Parquet, all columns as strings | `lake/raw/market_prices/run_id=.../` | Exactly what was extracted; immutable, one folder per run, so any run can be replayed |
| Curated zone | Parquet, typed, with `daily_return` and `is_outlier` | `lake/curated/market_prices/ticker=.../` | Cleaned history per ticker, merged by date on every run |
| Run metadata | JSON | `lake/manifests/<run_id>.json` | Row counts, source, failures, file paths, status |
| Serving | PostgreSQL | `market_prices` etc. | Constrained, indexed, queryable by SQL and the REST API |

- **Why Parquet over CSV:** columnar, typed (no re-parsing dates and numbers),
  compressed, and readable by Spark, DuckDB and warehouse loaders as-is.
- **Lake vs warehouse:** the lake keeps raw and curated files cheaply with
  loose structure; PostgreSQL plays the warehouse role (modelled tables,
  constraints, SQL). A cloud warehouse (BigQuery, Snowflake) is **not used**.
- **ETL and ELT together:** prices are transformed *before* loading into
  PostgreSQL (ETL), but the untouched extract is landed in the raw zone *before*
  any transformation (the EL step of ELT), so a bug in a transform rule can be
  fixed and the data re-processed without re-fetching from the provider.
- **Known gap:** `is_outlier` is stored in the curated Parquet files and counted
  in logs and manifests, but `market_prices` has no column for it, so the flag
  is not queryable in SQL. Adding it would be a one-column schema change.

## 5. Batch vs stream

The pipeline is **batch**: one run per day after market close
(`PIPELINE_SCHEDULE`), which matches end-of-day price data and daily portfolio
valuation. Streaming would earn its complexity for intraday ticks or real-time
risk limits. **Not implemented.** What would change: a message broker topic of
price ticks, a consumer applying the same cleaning and validation per
micro-batch, and an upsert into a latest-price store. The transform functions
are pure DataFrame functions, so they would be reused unchanged.

## 6. Data governance

| Pillar | Implemented | Not implemented |
|---|---|---|
| **Quality** | Row-level rules in `src/transform/clean.py`; database constraints; failures counted and reported per run (see table below) | Freshness alerts (nothing warns if the scheduler itself is down, and failed runs are only logged, not sent anywhere) |
| **Stewardship** | Single writer: only the pipeline writes prices, and the API has no write routes (a test enforces this) | Named data owners and a change process for rules |
| **Security** | `.env` is git-ignored and excluded from the Docker image; containers run as a non-root user; all SQL is parameterised; the API is read-only, published on localhost only, and can require an `X-API-Key` header (set `API_KEY`; `/health` stays open for health checks) | TLS, per-user access control, key rotation, encryption at rest. With `API_KEY` unset the API is open, which is the local demo default |
| **Management** | Lineage and replay: each run has a `run_id`, an immutable raw copy and a manifest; schema is versioned in git | Retention and archival policy, data catalogue |

### Quality dimensions and the checks behind them

| Dimension | Check |
|---|---|
| Validity | `validate_ohlcv` drops rows with non-positive prices, negative volume, `high < low`, or `high`/`low` not bracketing open and close. Database `CHECK`s cover percentages, dividends, asset classes and sectors, but **not** prices (see section 2) |
| Completeness | `clean_market_prices` drops or imputes missing values (rows dropped are logged); an API ticker that returns no rows is reported as a failure, not a silent success |
| Uniqueness | Primary keys on `(asset_id, price_date)`; idempotent upserts; the curated lake merges by date |
| Accuracy | `detect_price_outliers` flags (never drops) returns more than 3 standard deviations from a rolling 20-day window, because a real large move is information |
| Consistency | Foreign keys; the same cleaning path for CSV and API sources, since both extractors return identical columns |
| Timeliness | Scheduled daily run; run start and finish timestamps in each manifest. A run that loads nothing (for example the API answering with a quota message) is logged by the scheduler as FAILED and makes `python -m src.orchestration.run_pipeline` exit 1; a partial run logs a warning. No external alert is sent |
