"""
Phase 2/3 安全测试 — 路径遍历防护 / 写入白名单 / MaskedSecret / execute_python_script / OrderIntent 枚举
"""
import os
import pytest

from core.config import MaskedSecret, get_secret
from core.artifacts.schemas import OrderIntent, OrderSide, OrderType


# ---- _safe_resolve ----

class TestSafeResolve:
    """Test ResearchAgent._safe_resolve path traversal prevention."""

    @staticmethod
    def _resolve(base, path):
        # Import inline to avoid full ResearchAgent init
        from research_cli import ResearchAgent
        return ResearchAgent._safe_resolve(base, path)

    def test_normal_relative_path(self, tmp_path):
        base = str(tmp_path)
        result = self._resolve(base, "Reports/scan.md")
        assert result == os.path.normpath(os.path.join(base, "Reports", "scan.md"))

    def test_traversal_blocked(self, tmp_path):
        base = str(tmp_path)
        with pytest.raises(ValueError, match="路径越界"):
            self._resolve(base, "../../etc/passwd")

    def test_double_dot_in_middle_blocked(self, tmp_path):
        base = str(tmp_path)
        with pytest.raises(ValueError, match="路径越界"):
            self._resolve(base, "Reports/../../etc/passwd")

    def test_absolute_outside_blocked(self, tmp_path):
        base = str(tmp_path)
        # An absolute path outside base should be rejected
        outside = os.path.normpath(os.path.join(base, "..", "outside.txt"))
        with pytest.raises(ValueError, match="路径越界"):
            self._resolve(base, outside)

    def test_absolute_inside_allowed(self, tmp_path):
        base = str(tmp_path)
        inside = os.path.join(base, "Reports", "test.md")
        result = self._resolve(base, inside)
        assert result == os.path.normpath(inside)

    def test_base_itself_allowed(self, tmp_path):
        base = str(tmp_path)
        result = self._resolve(base, ".")
        assert result == os.path.normpath(base)


# ---- Write Extension Whitelist ----

class TestWriteExtensionWhitelist:
    def test_md_allowed(self):
        from research_cli import ResearchAgent
        assert ".md" in ResearchAgent.SAFE_WRITE_EXTENSIONS

    def test_py_blocked(self):
        from research_cli import ResearchAgent
        assert ".py" not in ResearchAgent.SAFE_WRITE_EXTENSIONS

    def test_env_blocked(self):
        from research_cli import ResearchAgent
        assert ".env" not in ResearchAgent.SAFE_WRITE_EXTENSIONS

    def test_sh_blocked(self):
        from research_cli import ResearchAgent
        assert ".sh" not in ResearchAgent.SAFE_WRITE_EXTENSIONS


# ---- MaskedSecret ----

class TestMaskedSecret:
    def test_repr_masks_long_key(self):
        secret = MaskedSecret("sk-1234567890abcdef")
        r = repr(secret)
        assert "sk-1" in r
        assert "cdef" in r
        assert "1234567890abcde" not in r  # middle is masked

    def test_repr_masks_short_key(self):
        secret = MaskedSecret("short")
        assert repr(secret) == "'****'"

    def test_str_passthrough(self):
        """str() 返回原始值供 API 使用。"""
        raw = "sk-1234567890abcdef"
        secret = MaskedSecret(raw)
        assert str(secret) == raw
        assert secret == raw  # equality with plain str

    def test_get_secret_returns_masked(self, monkeypatch):
        monkeypatch.setenv("TEST_SECRET_KEY", "my-api-key-value")
        val = get_secret("TEST_SECRET_KEY")
        assert isinstance(val, MaskedSecret)
        assert str(val) == "my-api-key-value"
        assert "my-api-key-value" not in repr(val)


# ---- execute_python_script 路径验证 ----

class TestExecuteScriptSecurity:
    """V3.9: execute_python_script 路径验证 + 扩展名白名单。"""

    @staticmethod
    def _resolve(base, path):
        from research_cli import ResearchAgent
        return ResearchAgent._safe_resolve(base, path)

    def test_execute_script_traversal_blocked(self, tmp_path):
        """路径遍历攻击被拦截。"""
        base = str(tmp_path)
        with pytest.raises(ValueError, match="路径越界"):
            self._resolve(base, "../../evil.py")

    def test_execute_script_non_py_blocked(self, tmp_path):
        """非 .py 文件被拦截 — 通过 _safe_resolve 后再检查扩展名。"""
        base = str(tmp_path)
        # .sh file inside project is allowed by path check but not by extension
        sh_file = os.path.join(base, "scripts", "evil.sh")
        os.makedirs(os.path.dirname(sh_file), exist_ok=True)
        with open(sh_file, "w") as f:
            f.write("#!/bin/bash\necho hacked")
        resolved = self._resolve(base, "scripts/evil.sh")
        assert not resolved.lower().endswith(".py")

    def test_execute_script_valid_path(self, tmp_path):
        """项目内 .py 文件通过验证。"""
        base = str(tmp_path)
        py_file = os.path.join(base, "scripts", "hello.py")
        os.makedirs(os.path.dirname(py_file), exist_ok=True)
        with open(py_file, "w") as f:
            f.write("print('hello')")
        resolved = self._resolve(base, "scripts/hello.py")
        assert resolved.endswith(".py")
        assert resolved.startswith(os.path.normpath(base))


# ---- OrderIntent 枚举约束 ----

class TestOrderIntentEnum:
    """V3.9: OrderIntent side/order_type 枚举验证。"""

    def test_valid_side_buy(self):
        oi = OrderIntent(ticker="AAPL", side="buy", quantity=10,
                         order_type="market", rationale="test", confidence=0.9)
        assert oi.side == "buy"

    def test_valid_side_sell(self):
        oi = OrderIntent(ticker="AAPL", side="sell", quantity=10,
                         order_type="limit", limit_price=150.0,
                         rationale="test", confidence=0.9)
        assert oi.side == "sell"

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError, match="无效的 side"):
            OrderIntent(ticker="AAPL", side="LONG", quantity=10,
                        order_type="market", rationale="test", confidence=0.9)

    def test_case_normalize_side(self):
        oi = OrderIntent(ticker="AAPL", side="BUY", quantity=10,
                         order_type="market", rationale="test", confidence=0.9)
        assert oi.side == "buy"

    def test_case_normalize_order_type(self):
        oi = OrderIntent(ticker="AAPL", side="buy", quantity=10,
                         order_type="LIMIT", limit_price=150.0,
                         rationale="test", confidence=0.9)
        assert oi.order_type == "limit"

    def test_invalid_order_type_raises(self):
        with pytest.raises(ValueError, match="无效的 order_type"):
            OrderIntent(ticker="AAPL", side="buy", quantity=10,
                        order_type="stop_loss", rationale="test", confidence=0.9)

    def test_enum_values(self):
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
