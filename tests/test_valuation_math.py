"""估值算术的确定性测试。

这些数字之所以值得测，正是因为它们原本靠模型心算——心算的结果无法回归，
一旦悄悄变了也没人知道。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "valuation_math.py"

sys.path.insert(0, str(PROJECT_ROOT))

from scripts.valuation_math import (  # noqa: E402
    _normalize_argv,
    enterprise_value,
    run_checks,
    solve_implied_growth,
)


class TestEnterpriseValue:
    def test_terminal_growth_above_discount_rate_is_rejected(self):
        with pytest.raises(ValueError, match="must exceed terminal_growth"):
            enterprise_value(1e9, 0.10, 0.03, 0.05, 10)

    def test_components_sum_to_total(self):
        result = enterprise_value(6e10, 0.20, 0.10, 0.03, 10)
        assert result["pv_explicit"] + result["pv_terminal"] == pytest.approx(
            result["enterprise_value"]
        )

    def test_tv_share_is_a_fraction(self):
        result = enterprise_value(6e10, 0.20, 0.10, 0.03, 10)
        assert 0.0 < result["tv_share_of_ev"] < 1.0

    def test_higher_growth_yields_higher_value(self):
        low = enterprise_value(1e9, 0.05, 0.10, 0.03, 10)["enterprise_value"]
        high = enterprise_value(1e9, 0.15, 0.10, 0.03, 10)["enterprise_value"]
        assert high > low


class TestSolveImpliedGrowth:
    def test_solution_reproduces_target_ev(self):
        """反解出来的增长率代回模型，必须还原目标企业价值。"""
        target = 3.2e12
        growth = solve_implied_growth(target, 6e10, 0.10, 0.03, 10)

        assert growth is not None
        rebuilt = enterprise_value(6e10, growth, 0.10, 0.03, 10)["enterprise_value"]
        assert rebuilt == pytest.approx(target, rel=1e-6)

    def test_non_positive_fcf_returns_none(self):
        assert solve_implied_growth(1e11, -5e9, 0.10, 0.03, 10) is None
        assert solve_implied_growth(1e11, 0.0, 0.10, 0.03, 10) is None

    def test_unreachable_target_returns_none_instead_of_guessing(self):
        # 目标价格远超搜索区间上限时必须如实返回 None，而不是给个凑出来的数
        assert solve_implied_growth(1e30, 1e3, 0.10, 0.03, 10) is None

    def test_cheaper_price_implies_lower_growth(self):
        expensive = solve_implied_growth(3.2e12, 6e10, 0.10, 0.03, 10)
        cheap = solve_implied_growth(1.5e12, 6e10, 0.10, 0.03, 10)
        assert cheap < expensive


class TestChecks:
    def test_terminal_above_discount_is_fail(self):
        checks = run_checks(0.03, 0.05, None, None, 1e9)
        failures = [c for c in checks if c["level"] == "FAIL"]
        assert any(c["check"] == "terminal_growth_below_discount_rate" for c in failures)

    def test_negative_fcf_is_fail(self):
        checks = run_checks(0.10, 0.03, 0.6, None, -1e9)
        assert any(
            c["check"] == "positive_base_cash_flow" and c["level"] == "FAIL" for c in checks
        )

    def test_sane_inputs_produce_no_findings(self):
        checks = run_checks(0.10, 0.03, 0.65, 0.15, 1e9)
        assert checks == []

    def test_extreme_implied_growth_warns(self):
        checks = run_checks(0.10, 0.03, 0.65, 0.95, 1e9)
        assert any(c["check"] == "implied_growth_plausible" for c in checks)

    def test_terminal_value_share_out_of_range_warns(self):
        checks = run_checks(0.10, 0.03, 0.95, 0.15, 1e9)
        assert any(c["check"] == "terminal_value_share" for c in checks)


class TestArgvNormalization:
    def test_negative_number_is_attached_to_its_option(self):
        assert _normalize_argv(["--net-debt", "-5e9"]) == ["--net-debt=-5e9"]

    def test_real_flags_are_left_alone(self):
        assert _normalize_argv(["--fcf", "1e9", "--no-sensitivity"]) == [
            "--fcf",
            "1e9",
            "--no-sensitivity",
        ]

    def test_option_followed_by_option_is_untouched(self):
        assert _normalize_argv(["--no-sensitivity", "--fcf", "1e9"]) == [
            "--no-sensitivity",
            "--fcf",
            "1e9",
        ]


class TestCli:
    """脚本被当作硬门用，退出码必须可靠。"""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_success_exits_zero_with_json(self):
        proc = self._run(
            "--market-cap", "3.2e12", "--shares", "2.44e10", "--fcf", "6e10", "--no-sensitivity"
        )
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        assert payload["status"] in ("success", "warn")
        assert payload["implied_growth"]["solved"] is True
        assert payload["margin_of_safety"]["value_per_share"] > 0

    def test_invalid_model_exits_nonzero(self):
        proc = self._run(
            "--market-cap", "1e11", "--fcf", "5e9",
            "--discount-rate", "0.03", "--terminal-growth", "0.05", "--no-sensitivity",
        )
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["status"] == "fail"

    def test_sensitivity_grid_is_emitted_by_default(self):
        proc = self._run("--market-cap", "3.2e12", "--shares", "2.44e10", "--fcf", "6e10")
        payload = json.loads(proc.stdout)
        assert payload["sensitivity"]["unit"] == "per_share"
        assert len(payload["sensitivity"]["rows"]) == 5
        assert len(payload["sensitivity"]["growth_steps"]) == 5

    def test_missing_market_cap_and_price_is_rejected(self):
        proc = self._run("--fcf", "6e10")
        assert proc.returncode != 0
