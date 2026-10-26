#!/usr/bin/env bash
# End-to-end check that a fresh clone works under Docker.
#
# Run from anywhere:   bash scripts/verify_clean_clone.sh
# WARNING: runs `docker compose down -v`, which DELETES the dev database volume.
#
# Steps: fresh stack -> seed -> pipeline -> rerun (idempotent) -> analytics SQL
#        -> scheduler container stays up and registers its job.
set -euo pipefail

cd "$(dirname "$0")/.."

step() { printf '\n==> %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || fail "docker not found"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin not found"

[ -f .env ] || { step "No .env found, copying .env.example"; cp .env.example .env; }
[ -f data/sample_prices.csv ] || fail "data/sample_prices.csv missing (run scripts/generate_sample_prices.py)"

# Read DB credentials the way compose does (.env value, else its default).
# Deliberately NOT `source .env`: values like PIPELINE_SCHEDULE=0 18 * * 1-5
# are valid for compose/dotenv but would be executed as shell code.
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d "\r" || true; }
PGUSER="$(env_get POSTGRES_USER)"; PGUSER="${PGUSER:-de27four}"
PGDB="$(env_get POSTGRES_DB)";     PGDB="${PGDB:-portfolio_analytics}"
psql_q() { docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" -tAc "$1"; }

step "Fresh stack (down -v, build, start Postgres and wait until healthy)"
docker compose down -v --remove-orphans
docker compose up -d --build --wait postgres

step "Schema applied by initdb?"
tables=$(psql_q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "$tables" -ge 7 ] || fail "expected >= 7 tables, found $tables"
echo "tables: $tables"

step "Seed (one-shot service)"
docker compose run --rm seed
assets=$(psql_q "SELECT count(*) FROM assets")
[ "$assets" -ge 1 ] || fail "no assets after seed"
echo "assets: $assets"

step "Pipeline run (one-shot service)"
docker compose run --rm app
rows=$(psql_q "SELECT count(*) FROM market_prices")
[ "$rows" -ge 1 ] || fail "no market_prices rows after pipeline run"
echo "market_prices rows: $rows"

step "Rerun pipeline: row count must not change (idempotent upsert)"
docker compose run --rm app
rows2=$(psql_q "SELECT count(*) FROM market_prices")
[ "$rows" = "$rows2" ] || fail "row count changed on rerun: $rows -> $rows2"

step "Analytics examples run without error"
docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 -q \
  < sql/analytics_examples.sql > /dev/null

step "Scheduler container starts and registers its job"
docker compose up -d scheduler
sleep 5
state=$(docker inspect -f '{{.State.Status}}' de27four_scheduler)
[ "$state" = "running" ] || { docker compose logs scheduler; fail "scheduler state is '$state'"; }
docker compose logs scheduler | grep -q "Scheduler started" || { docker compose logs scheduler; fail "scheduler did not report starting"; }

step "Container runs as non-root"
user=$(docker compose exec -T scheduler id -u)
[ "$user" != "0" ] || fail "scheduler is running as root"

printf '\nPASS: clean-clone verification succeeded (tables=%s assets=%s prices=%s)\n' "$tables" "$assets" "$rows"
echo "Stack left running. Stop it with: docker compose down"