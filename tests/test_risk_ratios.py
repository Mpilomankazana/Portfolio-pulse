"""Unit tests for src/analytics/risk_ratios.py."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.risk_ratios import calculate_sharpe_ratio, calculate_sortino_ratio


class TestCalculateSharpeRatio:
    def test_hand_calculated_zero_risk_free_rate(self):
        returns = [0.01, -0.02, 0.015, 0.005, -0.01]
        df = pd.DataFrame(
            [{"manager_id": 1, "date": f"2026-01-0{i + 1}", "daily_return": r}
             for i, r in enumerate(returns)]
        )
        result = calculate_sharpe_ratio(df)
        row = result.iloc[0]

        series = pd.Series(returns)
        expected = (series.mean() / series.std(ddof=1)) * np.sqrt(252)
        assert row["sharpe_ratio"] == pytest.approx(expected)

    def test_nonzero_risk_free_rate_is_deannualized(self):
        # A positive annual risk-free rate shifts the excess-return series
        # down, which should raise std-normalized distance from zero,
        # not just subtract a constant from the final ratio.
        returns = [0.01, -0.02, 0.015, 0.005, -0.01]
        df = pd.DataFrame(
            [{"manager_id": 1, "date": f"2026-01-0{i + 1}", "daily_return": r}
             for i, r in enumerate(returns)]
        )
        result = calculate_sharpe_ratio(df, risk_free_rate=0.05, trading_days_per_year=252)
        row = result.iloc[0]

        daily_rf = 0.05 / 252
        series = pd.Series(returns) - daily_rf
        expected = (series.mean() / series.std(ddof=1)) * np.sqrt(252)
        assert row["sharpe_ratio"] == pytest.approx(expected)

    def test_zero_variance_returns_nan_not_inf(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": 0.01},
        ])
        result = calculate_sharpe_ratio(df)
        row = result.iloc[0]
        assert np.isnan(row["sharpe_ratio"])

    def test_single_observation_returns_nan(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.02},
        ])
        result = calculate_sharpe_ratio(df)
        row = result.iloc[0]
        assert np.isnan(row["sharpe_ratio"])

    def test_nan_daily_return_treated_as_zero(self):
        df_with_nan = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": None},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": -0.02},
        ])
        df_with_zero = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.0},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": -0.02},
        ])
        result_nan = calculate_sharpe_ratio(df_with_nan)
        result_zero = calculate_sharpe_ratio(df_with_zero)
        assert result_nan.iloc[0]["sharpe_ratio"] == pytest.approx(
            result_zero.iloc[0]["sharpe_ratio"]
        )

    def test_multiple_managers_are_independent(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.02},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": 0.015},
            {"manager_id": 2, "date": "2026-01-01", "daily_return": -0.03},
            {"manager_id": 2, "date": "2026-01-02", "daily_return": -0.01},
            {"manager_id": 2, "date": "2026-01-03", "daily_return": -0.02},
        ])
        result = calculate_sharpe_ratio(df)
        m1 = result[result["manager_id"] == 1].iloc[0]
        m2 = result[result["manager_id"] == 2].iloc[0]
        # Manager 1 has consistently positive returns, manager 2
        # consistently negative — their Sharpe ratios should land on
        # opposite sides of zero.
        assert m1["sharpe_ratio"] > 0
        assert m2["sharpe_ratio"] < 0

    def test_higher_volatility_lowers_sharpe_for_same_mean_return(self):
        low_vol = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.010},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.012},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": 0.008},
        ])
        high_vol = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.05},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": -0.02},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": 0.007},
        ])
        low_vol_result = calculate_sharpe_ratio(low_vol).iloc[0]["sharpe_ratio"]
        high_vol_result = calculate_sharpe_ratio(high_vol).iloc[0]["sharpe_ratio"]
        assert low_vol_result > high_vol_result

    def test_empty_input_returns_empty_with_expected_columns(self):
        df = pd.DataFrame(columns=["manager_id", "date", "daily_return"])
        result = calculate_sharpe_ratio(df)
        assert len(result) == 0
        assert list(result.columns) == ["manager_id", "sharpe_ratio"]

    def test_custom_trading_days_per_year(self):
        returns = [0.01, -0.02, 0.015, 0.008, -0.005]
        df = pd.DataFrame(
            [{"manager_id": 1, "date": f"2026-01-0{i + 1}", "daily_return": r}
             for i, r in enumerate(returns)]
        )
        result_252 = calculate_sharpe_ratio(df, trading_days_per_year=252).iloc[0]["sharpe_ratio"]
        result_365 = calculate_sharpe_ratio(df, trading_days_per_year=365).iloc[0]["sharpe_ratio"]
        # Same series, different annualization factor -> different scale,
        # same sign.
        assert result_252 != pytest.approx(result_365)
        assert np.sign(result_252) == np.sign(result_365)


class TestCalculateSortinoRatio:
    def test_hand_calculated_zero_risk_free_rate(self):
        returns = [0.02, -0.01, 0.015, -0.03, 0.01]
        df = pd.DataFrame(
            [{"manager_id": 1, "date": f"2026-01-0{i + 1}", "daily_return": r}
             for i, r in enumerate(returns)]
        )
        result = calculate_sortino_ratio(df)
        row = result.iloc[0]

        series = pd.Series(returns)
        downside = series[series < 0]
        expected = (series.mean() / downside.std(ddof=1)) * np.sqrt(252)
        assert row["sortino_ratio"] == pytest.approx(expected)

    def test_ignores_upside_volatility_unlike_sharpe(self):
        # Same downside days, but one series has a huge upside swing.
        # Sortino should be identical between them since upside
        # volatility isn't penalized; Sharpe should differ.
        steady_upside = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": -0.02},
        ])
        big_upside = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.10},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": -0.02},
        ])
        # Downside deviation is computed from a single observation (-0.02)
        # in both cases, so std(ddof=1) of one point is NaN — use a
        # second downside day in each so the comparison is meaningful.
        steady_upside = pd.concat([
            steady_upside,
            pd.DataFrame([{"manager_id": 1, "date": "2026-01-04", "daily_return": -0.015}]),
        ])
        big_upside = pd.concat([
            big_upside,
            pd.DataFrame([{"manager_id": 1, "date": "2026-01-04", "daily_return": -0.015}]),
        ])

        steady_sortino = calculate_sortino_ratio(steady_upside).iloc[0]["sortino_ratio"]
        big_sortino = calculate_sortino_ratio(big_upside).iloc[0]["sortino_ratio"]
        steady_sharpe = calculate_sharpe_ratio(steady_upside).iloc[0]["sharpe_ratio"]
        big_sharpe = calculate_sharpe_ratio(big_upside).iloc[0]["sharpe_ratio"]

        # Downside deviation is the same in both (same two downside
        # days), but mean excess return differs because of the big
        # upside day, so Sortino isn't literally identical — the point
        # is that it moves only through the mean, not through a
        # volatility penalty the way Sharpe's std term does.
        assert big_sortino > steady_sortino
        # Sharpe, by contrast, is pulled down by the upside volatility
        # inflating std even though mean also rose — assert Sharpe's
        # relative lift is smaller than Sortino's, since only Sortino
        # is "rewarded" without a volatility penalty on the upside move.
        sortino_lift = big_sortino - steady_sortino
        sharpe_lift = big_sharpe - steady_sharpe
        assert sortino_lift > sharpe_lift

    def test_no_downside_observations_returns_nan(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.02},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": 0.005},
        ])
        result = calculate_sortino_ratio(df)
        row = result.iloc[0]
        assert np.isnan(row["sortino_ratio"])

    def test_single_downside_observation_returns_nan(self):
        # A single downside day has no ddof=1 std (division by zero
        # observations), so the ratio is undefined, not 0 or inf.
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": 0.02},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": -0.01},
        ])
        result = calculate_sortino_ratio(df)
        row = result.iloc[0]
        assert np.isnan(row["sortino_ratio"])

    def test_multiple_managers_are_independent(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-01", "daily_return": 0.02},
            {"manager_id": 1, "date": "2026-01-02", "daily_return": -0.01},
            {"manager_id": 1, "date": "2026-01-03", "daily_return": -0.015},
            {"manager_id": 2, "date": "2026-01-01", "daily_return": 0.01},
            {"manager_id": 2, "date": "2026-01-02", "daily_return": 0.02},
            {"manager_id": 2, "date": "2026-01-03", "daily_return": 0.005},
        ])
        result = calculate_sortino_ratio(df)
        m1 = result[result["manager_id"] == 1].iloc[0]
        m2 = result[result["manager_id"] == 2].iloc[0]
        # Manager 1 has downside days to compute a ratio from.
        assert not np.isnan(m1["sortino_ratio"])
        # Manager 2 has no downside days at all -> NaN, and must not
        # pick up manager 1's downside deviation or be dropped from
        # the result.
        assert np.isnan(m2["sortino_ratio"])

    def test_empty_input_returns_empty_with_expected_columns(self):
        df = pd.DataFrame(columns=["manager_id", "date", "daily_return"])
        result = calculate_sortino_ratio(df)
        assert len(result) == 0
        assert list(result.columns) == ["manager_id", "sortino_ratio"]