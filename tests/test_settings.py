"""
Phase 3 配置外部化测试 — settings 默认值 / 环境变量覆盖 / Guard 消费端
"""
import os
import pytest

from core import config
from core.config import get_float


# ---- get_float ----

class TestGetFloat:
    def test_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "3.14")
        assert get_float("TEST_FLOAT") == pytest.approx(3.14)

    def test_invalid_float_returns_default(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "not-a-number")
        assert get_float("TEST_FLOAT", 99.0) == 99.0

    def test_missing_returns_default(self):
        assert get_float("NONEXISTENT_FLOAT_VAR_12345", 42.0) == 42.0


# ---- Settings defaults ----

class TestSettingsDefaults:
    """不设环境变量时默认值与 V3.7 完全一致。"""

    def test_max_position_pct(self):
        from core import settings
        assert settings.execution.max_position_pct == pytest.approx(15.0)

    def test_cooldown_hours(self):
        from core import settings
        assert settings.execution.cooldown_hours == pytest.approx(24.0)

    def test_reverse_cooldown_days(self):
        from core import settings
        assert settings.execution.reverse_cooldown_days == 30

    def test_default_confidence(self):
        from core import settings
        assert settings.execution.default_confidence == pytest.approx(0.9)

    def test_preview_confidence(self):
        from core import settings
        assert settings.execution.preview_confidence == pytest.approx(1.0)

    def test_max_searches(self):
        from core import settings
        assert settings.search.max_searches == 8

    def test_budget_max(self):
        from core import settings
        assert settings.search.budget_max == 30

    def test_content_truncation(self):
        from core import settings
        assert settings.search.content_truncation == 300

    def test_tool_loop_max_iterations(self):
        from core import settings
        assert settings.tool_loop.max_iterations == 15


# ---- Guard uses settings ----

class TestGuardUsesSettings:
    def test_guard_no_arg_uses_settings(self):
        from services.execution.guards import MaxPositionGuard
        g = MaxPositionGuard()
        assert g.max_pct == pytest.approx(15.0)

    def test_guard_explicit_overrides(self):
        from services.execution.guards import MaxPositionGuard
        g = MaxPositionGuard(max_pct=20.0)
        assert g.max_pct == pytest.approx(20.0)

    def test_cooldown_guard_no_arg(self):
        from services.execution.guards import CooldownGuard
        g = CooldownGuard()
        assert g.cooldown_hours == pytest.approx(24.0)

    def test_reverse_cooldown_guard_no_arg(self):
        from services.execution.guards import ReverseCooldownGuard
        g = ReverseCooldownGuard()
        assert g.cooldown_days == 30


# ---- BudgetManager uses settings ----

class TestBudgetUsesSettings:
    def test_budget_default(self):
        from core.toolbus.budget import BudgetManager
        bm = BudgetManager()
        assert bm.max_budget == 30

    def test_budget_explicit_overrides(self):
        from core.toolbus.budget import BudgetManager
        bm = BudgetManager(max_budget=50)
        assert bm.max_budget == 50


# ---- Trigger Settings defaults (V3.9) ----

class TestTriggerSettingsDefaults:
    """V3.9: Trigger 配置默认值与 V3.8 硬编码一致。"""

    def test_morning_scan_cooldown(self):
        from core import settings
        assert settings.trigger.morning_scan_cooldown == 6 * 3600

    def test_position_review_cooldown(self):
        from core import settings
        assert settings.trigger.position_review_cooldown == 24 * 3600

    def test_price_move_threshold(self):
        from core import settings
        assert settings.trigger.price_move_threshold == pytest.approx(3.5)

    def test_price_move_cooldown(self):
        from core import settings
        assert settings.trigger.price_move_cooldown == 4 * 3600

    def test_earnings_cooldown(self):
        from core import settings
        assert settings.trigger.earnings_cooldown == 24 * 3600

    def test_earnings_window_days(self):
        from core import settings
        assert settings.trigger.earnings_window_days == 7


# ---- Trigger rules use settings (V3.9) ----

class TestTriggerRulesUseSettings:
    """V3.9: Trigger rules 消费 settings 默认值。"""

    def test_price_move_rule_default(self):
        from services.trigger.rules import PriceMoveTriggerRule
        rule = PriceMoveTriggerRule()
        assert rule.cooldown_seconds == 4 * 3600

    def test_price_move_rule_explicit(self):
        from services.trigger.rules import PriceMoveTriggerRule
        rule = PriceMoveTriggerRule(cooldown_seconds=7200)
        assert rule.cooldown_seconds == 7200

    def test_earnings_rule_default(self):
        from services.trigger.rules import EarningsUpcomingTriggerRule
        rule = EarningsUpcomingTriggerRule()
        assert rule.cooldown_seconds == 24 * 3600
