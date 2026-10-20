"""Unit tests for src/analytics/manager_performance.py."""
import pandas as pd
import pytest

from src.analytics.manager_performance import (
    calculate_quarterly_returns,
    rank_managers_by_performance,
)


class TestCalculateQuarterlyReturns:
    def test_hand_calculated_compounding(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-05", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-06", "daily_return": 0.02},
            {"manager_id": 1, "date": "2026-01-07", "daily_return": -0.005},
        ])
        result = calculate_quarterly_returns(df)
        row = result.iloc[0]
        expected = (1.01 * 1.02 * 0.995) - 1
        assert row["quarterly_return"] == pytest.approx(expected)
        assert row["year"] == 2026
        assert row["quarter"] == 1

    def test_compounding_not_summing(self):
        # If this summed instead of compounded, it would give exactly 0.03
        # rather than the slightly higher compounded figure — the gap
        # between the two is exactly what this test is meant to catch.
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-05", "daily_return": 0.01},
            {"manager_id": 1, "date": "2026-01-06", "daily_return": 0.02},
        ])
        result = calculate_quarterly_returns(df)
        row = result.iloc[0]
        naive_sum = 0.01 + 0.02
        assert row["quarterly_return"] != pytest.approx(naive_sum)
        assert row["quarterly_return"] == pytest.approx((1.01 * 1.02) - 1)

    def test_leading_nan_day_treated_as_zero_percent(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-05", "daily_return": None},  # first day, no prior close
            {"manager_id": 1, "date": "2026-01-06", "daily_return": 0.05},
        ])
        result = calculate_quarterly_returns(df)
        row = result.iloc[0]
        # NaN day contributes a factor of 1 (0%), so the quarter's return
        # is driven entirely by the one real return.
        assert row["quarterly_return"] == pytest.approx(0.05)

    def test_separate_quarters_for_same_manager_are_independent(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-15", "daily_return": 0.10},  # Q1
            {"manager_id": 1, "date": "2026-04-15", "daily_return": 0.20},  # Q2
        ])
        result = calculate_quarterly_returns(df)
        q1 = result[result["quarter"] == 1].iloc[0]
        q2 = result[result["quarter"] == 2].iloc[0]
        assert q1["quarterly_return"] == pytest.approx(0.10)
        assert q2["quarterly_return"] == pytest.approx(0.20)

    def test_multiple_managers_are_independent(self):
        df = pd.DataFrame([
            {"manager_id": 1, "date": "2026-01-15", "daily_return": 0.10},
            {"manager_id": 2, "date": "2026-01-15", "daily_return": -0.05},
        ])
        result = calculate_quarterly_returns(df)
        m1 = result[result["manager_id"] == 1].iloc[0]
        m2 = result[result["manager_id"] == 2].iloc[0]
        assert m1["quarterly_return"] == pytest.approx(0.10)
        assert m2["quarterly_return"] == pytest.approx(-0.05)

    def test_empty_input_returns_empty_with_expected_columns(self):
        df = pd.DataFrame(columns=["manager_id", "date", "daily_return"])
        result = calculate_quarterly_returns(df)
        assert len(result) == 0
        assert list(result.columns) == ["manager_id", "year", "quarter", "quarterly_return"]


class TestRankManagersByPerformance:
    def test_clear_ranking(self):
        df = pd.DataFrame([
            {"manager_id": 1, "year": 2026, "quarter": 1, "quarterly_return": 0.10},
            {"manager_id": 2, "year": 2026, "quarter": 1, "quarterly_return": 0.20},
            {"manager_id": 3, "year": 2026, "quarter": 1, "quarterly_return": 0.05},
        ])
        result = rank_managers_by_performance(df)
        best = result[result["manager_id"] == 2].iloc[0]
        middle = result[result["manager_id"] == 1].iloc[0]
        worst = result[result["manager_id"] == 3].iloc[0]
        assert best["rank"] == 1
        assert middle["rank"] == 2
        assert worst["rank"] == 3

    def test_tied_managers_share_min_rank(self):
        df = pd.DataFrame([
            {"manager_id": 1, "year": 2026, "quarter": 1, "quarterly_return": 0.10},
            {"manager_id": 2, "year": 2026, "quarter": 1, "quarterly_return": 0.10},
            {"manager_id": 3, "year": 2026, "quarter": 1, "quarterly_return": 0.05},
        ])
        result = rank_managers_by_performance(df)
        tied_a = result[result["manager_id"] == 1].iloc[0]
        tied_b = result[result["manager_id"] == 2].iloc[0]
        third = result[result["manager_id"] == 3].iloc[0]
        assert tied_a["rank"] == 1
        assert tied_b["rank"] == 1
        # method="min" means the next distinct manager gets rank 3, not 2.
        assert third["rank"] == 3

    def test_quarters_ranked_independently(self):
        df = pd.DataFrame([
            {"manager_id": 1, "year": 2026, "quarter": 1, "quarterly_return": 0.20},
            {"manager_id": 2, "year": 2026, "quarter": 1, "quarterly_return": 0.10},
            {"manager_id": 1, "year": 2026, "quarter": 2, "quarterly_return": 0.01},
            {"manager_id": 2, "year": 2026, "quarter": 2, "quarterly_return": 0.15},
        ])
        result = rank_managers_by_performance(df)
        q1_m1 = result[(result["manager_id"] == 1) & (result["quarter"] == 1)].iloc[0]
        q2_m1 = result[(result["manager_id"] == 1) & (result["quarter"] == 2)].iloc[0]
        assert q1_m1["rank"] == 1  # manager 1 led Q1
        assert q2_m1["rank"] == 2  # but trailed in Q2

    def test_empty_input_returns_empty_with_rank_column(self):
        df = pd.DataFrame(columns=["manager_id", "year", "quarter", "quarterly_return"])
        result = rank_managers_by_performance(df)
        assert len(result) == 0
        assert "rank" in result.columns