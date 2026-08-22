"""交叉验证核心逻辑测试 — 来源族独立性、偏差分档、市值验算。"""

import pytest

from core.price_consensus import (
    build_consensus,
    family_of,
    grade_deviation,
    verify_market_cap,
)


class TestFamilyOf:
    def test_yahoo_chain_is_one_family(self):
        assert family_of("fetch_market_prices") == "intl-vendor"
        assert family_of("yfinance") == "intl-vendor"
        assert family_of("yfinance:urllib_direct") == "intl-vendor"

    def test_cn_relays_share_a_family(self):
        for name in ("tencent", "eastmoney", "sina", "ths", "xueqiu", "tushare"):
            assert family_of(name) == "cn-exchange-relay"

    def test_unknown_source_is_not_merged_into_any_family(self):
        assert family_of("some-new-vendor") == "unknown"
        assert family_of("") == "unknown"


class TestGradeDeviation:
    @pytest.mark.parametrize(
        "deviation,expected",
        [(0.0, "consistent"), (1.0, "consistent"), (1.01, "minor"), (5.0, "minor"), (5.01, "major")],
    )
    def test_three_tiers(self, deviation, expected):
        assert grade_deviation(deviation) == expected


class TestBuildConsensus:
    def test_two_same_family_sources_do_not_count_as_crossed(self):
        """两次 Yahoo 读数不是交叉验证——这正是旧实现的假阳性。"""
        result = build_consensus([
            {"source": "fetch_market_prices", "value": 100.0},
            {"source": "yfinance:urllib_direct", "value": 100.4},
        ])
        assert result["passed"] is False
        assert result["grade"] == "single_family"
        assert result["independent_family_count"] == 1
        assert "单源未交叉" in result["verdict"]

    def test_cross_family_within_tolerance_passes(self):
        result = build_consensus([
            {"source": "fetch_market_prices", "value": 100.0},
            {"source": "tencent", "value": 100.4},
        ], tolerance_pct=1.0)
        assert result["passed"] is True
        assert result["independent_family_count"] == 2
        assert result["grade"] == "consistent"
        assert "已交叉" in result["verdict"]

    def test_identical_cross_family_values_are_treated_as_single_source(self):
        result = build_consensus([
            {"source": "fetch_market_prices", "value": 153.70},
            {"source": "tencent", "value": 153.70},
        ])
        assert result["identical_values"] is True
        assert result["passed"] is False
        assert result["grade"] == "suspect_same_source"
        assert "疑似同源" in result["verdict"]

    def test_identical_values_can_be_accepted_explicitly(self):
        result = build_consensus([
            {"source": "fetch_market_prices", "value": 153.70},
            {"source": "tencent", "value": 153.70},
        ], allow_identical=True)
        assert result["passed"] is True

    def test_divergence_beyond_tolerance_fails_and_reports_deviation(self):
        result = build_consensus([
            {"source": "fetch_market_prices", "value": 100.0},
            {"source": "tencent", "value": 130.0},
        ], tolerance_pct=1.0)
        assert result["passed"] is False
        assert result["grade"] == "major"          # 偏离中位数 13% > 5%
        assert result["max_deviation_pct"] == pytest.approx(13.0434, abs=1e-3)
        assert "来源不一致" in result["verdict"]

    def test_moderate_divergence_lands_in_the_middle_tier(self):
        result = build_consensus([
            {"source": "fetch_market_prices", "value": 100.0},
            {"source": "tencent", "value": 108.0},
        ], tolerance_pct=1.0)
        assert result["passed"] is False
        assert result["grade"] == "minor"          # 偏离中位数 3.85%，落在 1~5% 档
        assert result["max_deviation_pct"] == pytest.approx(3.8461, abs=1e-3)

    def test_minor_divergence_is_graded_between_one_and_five_pct(self):
        result = build_consensus([
            {"source": "eastmoney", "value": 100.0},
            {"source": "yfinance", "value": 103.0},
        ], tolerance_pct=1.0)
        assert result["grade"] == "minor"
        assert result["passed"] is False

    def test_consensus_uses_median_not_mean(self):
        result = build_consensus([
            {"source": "eastmoney", "value": 100.0},
            {"source": "yfinance", "value": 101.0},
            {"source": "finmind", "value": 500.0},
        ], tolerance_pct=1.0)
        assert result["consensus"] == 101.0

    def test_no_numeric_sample_returns_no_data(self):
        result = build_consensus([{"source": "tencent", "value": None}])
        assert result["grade"] == "no_data"
        assert result["passed"] is False
        assert result["consensus"] is None

    def test_metric_label_and_unit_flow_into_verdict(self):
        result = build_consensus(
            [{"source": "eastmoney", "value": 1239}, {"source": "cninfo", "value": 1241}],
            label="营收",
            unit="亿",
        )
        assert result["verdict"].startswith("营收证据：")
        assert "亿" in result["verdict"]


class TestVerifyMarketCap:
    def test_matching_cap_passes(self):
        result = verify_market_cap(price=510, shares=9.11e9, reported_cap=510 * 9.11e9, currency="HKD")
        assert result["passed"] is True
        assert result["deviation_pct"] == pytest.approx(0.0, abs=1e-6)
        assert "✅" in result["verdict"]

    def test_cap_mismatch_beyond_tolerance_fails(self):
        result = verify_market_cap(price=100, shares=1e9, reported_cap=2e11)
        assert result["passed"] is False
        assert result["deviation_pct"] == pytest.approx(50.0)
        assert "股本口径" in result["verdict"]

    def test_non_numeric_input_is_rejected(self):
        assert verify_market_cap(price="abc", shares=1, reported_cap=1)["passed"] is False

    def test_zero_reported_cap_is_rejected(self):
        assert verify_market_cap(price=10, shares=10, reported_cap=0)["passed"] is False
