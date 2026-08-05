"""
V3.9 工具函数测试 — ToolFactory 独立测试覆盖

覆盖文件操作、脚本执行、搜索、交易、浏览器工具。
"""
import json
import os
import types
from unittest.mock import MagicMock, patch

import pytest

from core.tool_factory import ToolFactory


# ---- Fixtures ----

@pytest.fixture
def factory(tmp_path):
    """构造一个 ToolFactory 实例，使用 tmp_path 作为 project_root。"""
    data_mgr = MagicMock()
    data_hub = MagicMock()
    data_hub._sources = {}
    ledger = MagicMock()
    kill_switch = MagicMock()
    guard_chain = MagicMock()
    execution_pipeline = MagicMock()
    f = ToolFactory(
        data_mgr=data_mgr,
        data_hub=data_hub,
        ledger=ledger,
        kill_switch=kill_switch,
        guard_chain=guard_chain,
        execution_pipeline=execution_pipeline,
        project_root=str(tmp_path),
    )
    return f


# ---- 文件操作工具 ----

class TestReadFile:
    def test_read_file_normal(self, factory, tmp_path):
        """读取存在的文件。"""
        test_file = tmp_path / "test.md"
        test_file.write_text("hello world", encoding="utf-8")
        result = factory.read_file("test.md")
        assert result == "hello world"

    def test_read_file_not_found(self, factory):
        """不存在文件返回错误信息（非抛异常）。"""
        result = factory.read_file("nonexistent.md")
        assert "File not found" in result

    def test_read_file_traversal(self, factory, tmp_path):
        """路径遍历被拦截。"""
        result = factory.read_file("../../etc/passwd")
        assert "Access denied" in result

    def test_report_write_is_blocked_when_quality_gate_fails(self, factory, tmp_path):
        result = factory.write_to_file("Reports/20260604/thin.md", "thin report")

        assert "Report quality gate failed" in result
        assert not (tmp_path / "Reports" / "20260604" / "thin.md").exists()

    def test_report_write_allows_quality_checked_report(self, factory, tmp_path):
        report = """# NVDA Buy Audit

## 结论先行
结论：等待。置信度：中。

## 实时数据快照
- NVDA price: 100.0, source: yfinance, fetched_at: 2026-06-04T12:00:00Z

## 证据台账
| 判断 | 证据 | 来源 | 日期 |
| --- | --- | --- | --- |
| 估值偏高 | Forward PE 高于历史中位数 | source: test | 2026-06-04 |

## Bull/Base/Bear
- Bull: EPS 上修。
- Base: 估值消化。
- Bear: 增长放缓。

## 行动计划
等待回落到行动价后再评估。

## 风险与不确定性
- 数据源可能延迟。

## 质量自检
- 已检查来源、日期、反方观点和行动计划。
"""
        result = factory.write_to_file("Reports/20260604/good.md", report)

        assert "Successfully saved" in result
        assert (tmp_path / "Reports" / "20260604" / "good.md").exists()

    def test_buy_report_conflicting_with_quick_requires_explanation(self, factory, tmp_path):
        reports_dir = tmp_path / "Reports" / "20260604"
        reports_dir.mkdir(parents=True)
        quick = """# 20260604 中钨高新 Quick

## 结论先行
结论：逢低买入。钨价持续飙升，黑钨精矿连涨。

## 实时数据快照
- 000657.SZ price: 74.0, source: yfinance, fetched_at: 2026-06-04T12:00:00Z

## 证据台账
| 判断 | 证据 | 来源 | 日期 |
| --- | --- | --- | --- |
| 钨价方向 | 黑钨精矿连涨 | source: test | 2026-06-04 |

## Bull/Base/Bear
- Bull: 钨价继续上涨。
- Base: 钨价震荡。
- Bear: 钨价下跌。

## 行动计划
逢低买入。

## 风险与不确定性
- 数据源存在延迟。

## 质量自检
- 已检查。
"""
        (reports_dir / "20260604_000657.SZ_Quick.md").write_text(quick, encoding="utf-8")
        buy = quick.replace("逢低买入。钨价持续飙升，黑钨精矿连涨。", "驳回。钨价腰斩下跌，黑钨精矿崩塌。")

        result = factory.write_to_file("Reports/20260604/20260604_000657.SZ_Buy.md", buy)

        assert "Report quality gate failed" in result
        assert "unexplained_conflict_with_prior_report" in result
        assert not (reports_dir / "20260604_000657.SZ_Buy.md").exists()


class TestWriteFile:
    def test_write_file_safe_ext(self, factory, tmp_path):
        """.md 可写。"""
        result = factory.write_to_file("output.md", "content")
        assert "Successfully saved" in result
        assert (tmp_path / "output.md").read_text(encoding="utf-8") == "content"

    def test_write_file_blocked_ext(self, factory):
        """.py 被拒绝。"""
        result = factory.write_to_file("evil.py", "import os")
        assert "写入被拒绝" in result

    def test_write_file_traversal(self, factory):
        """路径遍历被拦截。"""
        result = factory.write_to_file("../../evil.md", "hacked")
        assert "Access denied" in result


class TestListDir:
    def test_list_dir_normal(self, factory, tmp_path):
        """正常列目录。"""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("x", encoding="utf-8")
        result = factory.list_dir(".")
        assert "subdir" in result
        assert "file.txt" in result

    def test_list_dir_traversal(self, factory):
        """路径遍历被拦截。"""
        result = factory.list_dir("../../")
        assert "Access denied" in result


# ---- 脚本执行 ----

class TestExecuteScript:
    def test_execute_script_valid(self, factory, tmp_path):
        """合法 .py 脚本执行。"""
        script = tmp_path / "hello.py"
        script.write_text("print('hello from script')", encoding="utf-8")
        result = factory.execute_python_script("hello.py")
        assert "hello from script" in result

    def test_execute_script_traversal(self, factory):
        """路径遍历被拦截。"""
        result = factory.execute_python_script("../../evil.py")
        assert "安全拒绝" in result

    def test_execute_script_non_py(self, factory, tmp_path):
        """非 .py 拒绝。"""
        sh_file = tmp_path / "run.sh"
        sh_file.write_text("#!/bin/bash\necho hacked", encoding="utf-8")
        result = factory.execute_python_script("run.sh")
        assert "安全拒绝" in result
        assert ".py" in result

    def test_execute_script_timeout(self, factory, tmp_path):
        """超时返回错误。"""
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(300)", encoding="utf-8")
        # 使用 mock 来模拟超时，避免真正等待
        with patch("core.tool_factory.subprocess.run", side_effect=Exception("timed out")):
            result = factory.execute_python_script("slow.py")
        assert "Execution Failed" in result


# ---- 搜索工具 ----

class TestSearchWeb:
    def test_search_web_brave_fallback(self, factory):
        """Tavily 失败降级 Brave。"""
        factory.data_mgr.search_web.return_value = "搜索错误: API 配额已用完"
        factory.data_mgr.search_brave.return_value = "Brave results for query"
        result = factory.search_web("test query")
        assert "Brave" in result
        assert "Brave results" in result

    def test_search_web_normal(self, factory):
        """正常搜索返回结果。"""
        factory.data_mgr.search_web.return_value = "search result"
        result = factory.search_web("test")
        assert result == "search result"

    def test_search_web_quota_exhausted_brave_fails(self, factory):
        """配额用尽且 Brave 也失败时返回原始错误。"""
        factory.data_mgr.search_web.return_value = "配额已用完"
        factory.data_mgr.search_brave.return_value = "[Error: no key"
        result = factory.search_web("test")
        assert "配额已用完" in result


# ---- 交易工具 ----

class TestPreviewTrade:
    def test_preview_trade_passes(self, factory):
        """预览通过。"""
        factory.kill_switch.is_active.return_value = False
        factory.guard_chain.run.return_value = MagicMock(passed=True)
        result = factory.preview_trade("AAPL", "buy", 10, 150.0)
        assert "Passed" in result

    def test_preview_trade_kill_switch(self, factory):
        """KillSwitch 拒绝。"""
        factory.kill_switch.is_active.return_value = True
        factory.kill_switch.status.return_value = {"reason": "emergency"}
        result = factory.preview_trade("AAPL", "buy", 10, 150.0)
        assert "KillSwitch" in result

    def test_execute_trade_invalid_side(self, factory):
        """无效 side 被拦截（通过 OrderIntent 验证）。"""
        result = factory.execute_trade("AAPL", "LONG", 10, "market", 150.0, "test")
        assert "Rejected" in result or "无效" in result or "Pipeline Rejected" in result


class TestPortfolioSnapshot:
    def test_snapshot_empty(self, factory):
        """空组合返回合法 JSON。"""
        factory.data_mgr.fetch_market_prices.return_value = []
        snapshot_mock = MagicMock()
        snapshot_mock.to_dict.return_value = {"total_nav": 0, "cash": 0, "positions": []}
        factory.ledger.current_snapshot.return_value = snapshot_mock
        result = factory.get_portfolio_snapshot()
        data = json.loads(result)
        assert data["total_nav"] == 0
        assert data["positions"] == []


class TestRealtimeMarketTools:
    def test_get_realtime_quote_returns_structured_json(self, factory):
        factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "NVDA", "name": "NVIDIA", "price": 100.0, "change": 2.5}
        ]

        result = factory.get_realtime_quote("nvda")
        data = json.loads(result)

        assert data["ticker"] == "NVDA"
        assert data["price"] == 100.0
        assert data["source"] == "fetch_market_prices"
        assert "fetched_at" in data

    def test_cross_validate_price_marks_consensus_when_sources_are_close(self, factory):
        factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "NVDA", "price": 100.0, "change": 0.5}
        ]
        factory.data_hub._sources = {"yfinance": types.SimpleNamespace(available=True)}
        factory.data_hub.fetch.return_value = types.SimpleNamespace(
            data={"ticker": "NVDA", "price": 100.4, "source_method": "urllib_direct"}
        )

        result = factory.cross_validate_price("NVDA", tolerance_pct=1.0)
        data = json.loads(result)

        assert data["ticker"] == "NVDA"
        assert data["passed"] is True
        assert len(data["sources"]) == 2

    def test_check_report_quality_exposes_gate_result(self, factory):
        result = factory.check_report_quality("thin report")
        data = json.loads(result)

        assert data["passed"] is False
        assert "missing_sections" in data


# ---- 浏览器工具 ----

class TestBrowserFetch:
    def test_browser_fetch_error_handling(self, factory):
        """网络错误返回错误信息。"""
        factory.data_hub._sources = {
            "opencli": types.SimpleNamespace(available=True),
            "bb-browser": types.SimpleNamespace(available=False),
        }
        factory.data_hub.fetch.side_effect = ConnectionError("network down")
        factory.data_mgr.search_web.return_value = "fallback result"
        result = factory.browser_fetch(site="xueqiu", command="search")
        assert "downgraded to web search" in result
        assert "network down" in result
        assert "fallback result" in result

    def test_browser_fetch_returns_structured_result_when_available(self, factory):
        factory.data_hub._sources = {
            "opencli": types.SimpleNamespace(available=True),
        }
        factory.data_hub.fetch.return_value = types.SimpleNamespace(
            data={"results": [{"symbol": "NVDA"}]}
        )

        result = factory.browser_fetch(site="xueqiu", command="search", query="NVDA")

        assert json.loads(result)["results"][0]["symbol"] == "NVDA"
        factory.data_mgr.search_web.assert_not_called()


# ---- get_tools ----

class TestGetTools:
    def test_get_tools_returns_16(self, factory):
        """get_tools 返回当前公开的 13 个工具函数。"""
        tools = factory.get_tools()
        assert len(tools) == 16
        # 所有条目都是 callable
        for tool in tools:
            assert callable(tool)

    def test_get_tools_names(self, factory):
        """工具函数名称正确。"""
        tools = factory.get_tools()
        names = [t.__name__ if hasattr(t, '__name__') else t.__func__.__name__ for t in tools]
        expected = [
            "search_web", "read_file", "list_dir", "write_to_file",
            "get_realtime_quote", "cross_validate_price", "check_report_quality",
            "get_portfolio_snapshot", "preview_trade", "execute_trade",
            "execute_python_script", "browser_fetch", "drill_source",
            "browser_operate", "system_doctor", "learn_source",
        ]
        assert names == expected
