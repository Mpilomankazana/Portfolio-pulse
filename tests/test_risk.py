"""Unit tests for src/analytics/risk.py. Expected values are hand-derived."""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from src.analytics.risk import calculate_cvar, calculate_var, compare_to_benchmark


@pytest.fixture
def returns_100():
    # -10%, -9%, ..., +89% in 1% steps -> 100 observations, simple to reason about.
    return pd.Series([(i - 10) / 100 for i in range(100)])


class TestCalculateVar:
    def test_historical_matches_numpy_quantile(self, returns_100):
        expected = -np.quantile(returns_100, 0.05)  # 5th percentile of the sample
        assert calculate_var(returns_100, 0.95) == pytest.approx(max(0.0, expected))

    def test_historical_known_loss(self):
        # 20 observations; the 5% quantile interpolates between the two worst.
        r = pd.Series([-0.04, -0.03] + [0.01] * 18)
        expected = -np.quantile(r, 0.05)
        assert calculate_var(r, 0.95) == pytest.approx(expected)
        assert calculate_var(r, 0.95) > 0

    def test_parametric_matches_formula(self):
        r = pd.Series([0.01, -0.02, 0.015, -0.005, 0.0, -0.01, 0.02, -0.015])
        z = NormalDist().inv_cdf(0.05)
        expected = -(r.mean() + z * r.std(ddof=1))
        assert calculate_var(r, 0.95, "parametric") == pytest.approx(expected)

    def test_higher_confidence_means_larger_var(self):
        rng = np.random.default_rng(1)
        r = pd.Series(rng.normal(0, 0.01, 500))
        assert calculate_var(r, 0.99) > calculate_var(r, 0.95)

    def test_all_gains_clamps_to_zero(self):
        assert calculate_var(pd.Series([0.01, 0.02, 0.03, 0.04]), 0.95) == 0.0

    def test_nan_and_inf_are_ignored(self):
        clean = pd.Series([-0.03, 0.01, 0.02, -0.01, 0.0])
        dirty = pd.Series([-0.03, np.nan, 0.01, np.inf, 0.02, -0.01, -np.inf, 0.0])
        assert calculate_var(dirty, 0.9) == pytest.approx(calculate_var(clean, 0.9))

    @pytest.mark.parametrize("bad", [0, 1, -0.1, 1.5])
    def test_rejects_bad_confidence(self, bad):
        with pytest.raises(ValueError):
            calculate_var(pd.Series([0.01, -0.01]), bad)

    def test_rejects_unknown_method(self):
        with pytest.raises(ValueError):
            calculate_var(pd.Series([0.01, -0.01]), 0.95, "monte-carlo")

    def test_rejects_empty_and_all_nan(self):
        with pytest.raises(ValueError):
            calculate_var(pd.Series([], dtype=float))
        with pytest.raises(ValueError):
            calculate_var(pd.Series([np.nan, np.nan]))

    def test_parametric_needs_two_observations(self):
        with pytest.raises(ValueError):
            calculate_var(pd.Series([0.01]), 0.95, "parametric")


class TestCalculateCvar:
    def test_hand_calculated(self):
        # 20 obs: cutoff (5% quantile) = -0.0305, only -0.04 is at/below it.
        r = pd.Series([-0.04, -0.03] + [0.01] * 18)
        assert calculate_cvar(r, 0.95) == pytest.approx(0.04)

    def test_cvar_at_least_var(self):
        rng = np.random.default_rng(7)
        r = pd.Series(rng.standard_t(4, 1000) * 0.01)
        assert calculate_cvar(r, 0.95) >= calculate_var(r, 0.95)

    def test_all_gains_clamps_to_zero(self):
        assert calculate_cvar(pd.Series([0.01, 0.02, 0.03]), 0.95) == 0.0


class TestCompareToBenchmark:
    def test_portfolio_equal_to_benchmark(self):
        idx = pd.date_range("2026-01-01", periods=6)
        b = pd.Series([0.01, -0.02, 0.015, 0.0, 0.005, -0.01], index=idx)
        out = compare_to_benchmark(b, b)
        assert out["beta"] == pytest.approx(1.0)
        assert out["alpha_annualized"] == pytest.approx(0.0, abs=1e-12)
        assert out["excess_return_annualized"] == pytest.approx(0.0, abs=1e-12)
        assert out["tracking_error"] == pytest.approx(0.0, abs=1e-12)
        assert math.isnan(out["information_ratio"])  # zero tracking error
        assert out["correlation"] == pytest.approx(1.0)
        assert out["n_periods"] == 6

    def test_portfolio_is_twice_benchmark_gives_beta_two(self):
        idx = pd.date_range("2026-01-01", periods=6)
        b = pd.Series([0.01, -0.02, 0.015, 0.0, 0.005, -0.01], index=idx)
        out = compare_to_benchmark(2 * b, b)
        assert out["beta"] == pytest.approx(2.0)
        assert out["alpha_annualized"] == pytest.approx(0.0, abs=1e-12)  # rf = 0, exact leverage
        assert out["correlation"] == pytest.approx(1.0)
        assert out["excess_return_annualized"] == pytest.approx(b.mean() * 252)

    def test_constant_outperformance_alpha_and_excess(self):
        idx = pd.date_range("2026-01-01", periods=5)
        b = pd.Series([0.01, -0.01, 0.02, -0.02, 0.0], index=idx)
        out = compare_to_benchmark(b + 0.001, b)
        assert out["beta"] == pytest.approx(1.0)
        assert out["excess_return_annualized"] == pytest.approx(0.001 * 252)
        assert out["alpha_annualized"] == pytest.approx(0.001 * 252)
        assert out["tracking_error"] == pytest.approx(0.0, abs=1e-12)

    def test_information_ratio_hand_calculated(self):
        idx = pd.date_range("2026-01-01", periods=4)
        b = pd.Series([0.0, 0.0, 0.0, 0.0], index=idx)
        p = pd.Series([0.01, 0.03, 0.01, 0.03], index=idx)
        out = compare_to_benchmark(p, b, periods_per_year=4)
        active = p - b
        te = active.std(ddof=1) * 2  # sqrt(4)
        assert out["tracking_error"] == pytest.approx(te)
        assert out["information_ratio"] == pytest.approx((active.mean() * 4) / te)
        assert math.isnan(out["beta"])  # flat benchmark: undefined
        assert math.isnan(out["correlation"])

    def test_risk_free_rate_changes_alpha_not_beta(self):
        idx = pd.date_range("2026-01-01", periods=6)
        b = pd.Series([0.01, -0.02, 0.015, 0.0, 0.005, -0.01], index=idx)
        p = 0.5 * b + 0.002
        a0 = compare_to_benchmark(p, b, risk_free_rate=0.0)
        a1 = compare_to_benchmark(p, b, risk_free_rate=0.10)
        assert a0["beta"] == pytest.approx(a1["beta"])
        assert a0["alpha_annualized"] != pytest.approx(a1["alpha_annualized"])

    def test_aligns_on_index_and_drops_unshared_periods(self):
        p = pd.Series([0.01, 0.02, 0.03], index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
        b = pd.Series([0.0, 0.01, 0.02], index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"]))
        assert compare_to_benchmark(p, b)["n_periods"] == 2

    def test_too_few_periods_raises(self):
        p = pd.Series([0.01], index=pd.to_datetime(["2026-01-01"]))
        with pytest.raises(ValueError):
            compare_to_benchmark(p, p)

    def test_bad_periods_per_year_raises(self):
        s = pd.Series([0.01, 0.02])
        with pytest.raises(ValueError):
            compare_to_benchmark(s, s, periods_per_year=0)