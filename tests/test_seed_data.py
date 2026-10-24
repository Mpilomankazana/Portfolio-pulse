"""Consistency checks on the demo data: no database needed.

These catch the mistakes that would otherwise only surface as a DB
constraint error mid-seed, or as silently skipped tickers in the pipeline.
"""
import pandas as pd
import pytest

from src.extract.market_data import extract_from_csv
from src.orchestration import config, seed
from src.transform.clean import (
    calculate_daily_returns,
    clean_market_prices,
    detect_price_outliers,
    validate_ohlcv,
)

VALID_CLASSES = {"Equities", "Fixed Income", "Cash"}
VALID_SECTORS = {"Consumer Electronics", "Energy", "Entertainment", "Financials", "Healthcare", "Technology"}


@pytest.fixture(scope="module")
def sample_df():
    return extract_from_csv(str(config.CSV_SOURCES[0]))


def test_assets_use_allowed_classes_and_sectors():
    for ticker, asset_class, sector in seed.ASSETS:
        assert asset_class in VALID_CLASSES, ticker
        assert sector is None or sector in VALID_SECTORS, ticker


def test_every_sample_csv_ticker_is_seeded(sample_df):
    seeded = {t for t, _, _ in seed.ASSETS}
    assert set(sample_df["ticker"]) <= seeded


def test_holding_weights_sum_to_100_per_portfolio():
    for firm, rows in seed.HOLDINGS.items():
        assert sum(w for _, w, _, _ in rows) == pytest.approx(100.0), firm


def test_targets_sum_to_100_per_portfolio():
    for firm, targets in seed.TARGETS.items():
        assert sum(targets.values()) == pytest.approx(100.0), firm
        assert set(targets) <= VALID_CLASSES


def test_portfolio_allocations_sum_to_100():
    assert sum(m[3] for m in seed.MANAGERS) == pytest.approx(100.0)


def test_holdings_and_dividends_reference_seeded_tickers_and_managers():
    seeded = {t for t, _, _ in seed.ASSETS}
    firms = {m[0] for m in seed.MANAGERS}
    assert set(seed.HOLDINGS) == firms == set(seed.TARGETS)
    for rows in seed.HOLDINGS.values():
        assert {t for t, *_ in rows} <= seeded
    assert {t for t, _, _ in seed.DIVIDENDS} <= seeded


def test_sample_csv_passes_the_full_transform_chain_without_drops(sample_df):
    cleaned = clean_market_prices(sample_df)
    validated = validate_ohlcv(cleaned)
    result = detect_price_outliers(calculate_daily_returns(validated))

    assert len(cleaned) == len(sample_df)
    assert len(validated) == len(cleaned), "sample data should have no structurally invalid rows"
    assert "is_outlier" in result
    assert not result.duplicated(subset=["ticker", "date"]).any()


def test_generator_is_deterministic():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_prices.py"
    spec = importlib.util.spec_from_file_location("gen", path)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    on_disk = pd.read_csv(config.CSV_SOURCES[0])
    pd.testing.assert_frame_equal(gen.generate(), on_disk, check_dtype=False, rtol=1e-9)