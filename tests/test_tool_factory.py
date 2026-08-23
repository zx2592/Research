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

    def test_cross_validate_price_rejects_two_reads_of_the_same_family(self, factory):
        """fetch_market_prices 与 yfinance 都走 Yahoo chart API，同族不算交叉。"""
        factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "NVDA", "price": 100.0, "change": 0.5}
        ]
        factory.data_hub._sources = {"yfinance": types.SimpleNamespace(available=True)}
        factory.data_hub.fetch.return_value = types.SimpleNamespace(
            data={"ticker": "NVDA", "price": 100.4, "source_method": "urllib_direct"}
        )

        data = json.loads(factory.cross_validate_price("NVDA", tolerance_pct=1.0))

        assert data["ticker"] == "NVDA"
        assert data["passed"] is False
        assert data["grade"] == "single_family"
        assert data["independent_family_count"] == 1
        assert len(data["sources"]) == 2
        assert "单源未交叉" in data["verdict"]

    def test_cross_validate_price_passes_across_independent_families(self, factory):
        factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "600519", "price": 1500.0, "change": 0.5}
        ]
        factory.data_hub._sources = {"tencent": types.SimpleNamespace(available=True)}
        factory.data_hub.fetch.return_value = types.SimpleNamespace(
            data={"ticker": "600519", "price": 1504.0, "source_method": "qt.gtimg.cn"}
        )

        data = json.loads(factory.cross_validate_price("600519", tolerance_pct=1.0))

        assert data["passed"] is True
        assert data["independent_family_count"] == 2
        assert data["consensus_price"] == 1502.0
        assert "已交叉" in data["verdict"]
        assert data["spread_pct"] is not None   # 旧字段保持可读

    def test_cross_validate_price_flags_identical_cross_family_values(self, factory):
        factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "600519", "price": 1500.0, "change": 0.0}
        ]
        factory.data_hub._sources = {"tencent": types.SimpleNamespace(available=True)}
        factory.data_hub.fetch.return_value = types.SimpleNamespace(
            data={"ticker": "600519", "price": 1500.0, "source_method": "qt.gtimg.cn"}
        )

        data = json.loads(factory.cross_validate_price("600519"))

        assert data["identical_values"] is True
        assert data["passed"] is False
        assert data["grade"] == "suspect_same_source"

    def test_cross_validate_price_reports_single_numeric_source(self, factory):
        factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "NVDA", "price": 100.0, "change": 0.5}
        ]
        factory.data_hub._sources = {}

        data = json.loads(factory.cross_validate_price("NVDA"))

        assert data["passed"] is False
        assert data["error"] == "fewer than two price sources returned numeric prices"


class TestMetricCrossValidation:
    def test_cross_validate_metric_grades_and_returns_consensus(self, factory):
        data = json.loads(factory.cross_validate_metric(
            field="营收",
            values='{"东方财富": 1239, "巨潮年报": 1241, "stockanalysis": 1237}',
            unit="亿",
        ))
        assert data["field"] == "营收"
        assert data["consensus"] == 1239
        assert data["grade"] == "consistent"

    def test_cross_validate_metric_flags_major_divergence(self, factory):
        data = json.loads(factory.cross_validate_metric(
            field="净利润",
            values='{"GAAP": 245, "Non-GAAP": 400}',
            unit="亿",
        ))
        assert data["grade"] == "major"
        assert data["passed"] is False

    def test_cross_validate_metric_rejects_malformed_values(self, factory):
        data = json.loads(factory.cross_validate_metric(field="营收", values="not json"))
        assert "error" in data


class TestMarketCapVerification:
    def test_verify_market_cap_passes_when_consistent(self, factory):
        data = json.loads(factory.verify_market_cap(price=510, shares=9.11e9, reported_cap=510 * 9.11e9, currency="HKD"))
        assert data["passed"] is True

    def test_verify_market_cap_flags_share_count_mismatch(self, factory):
        data = json.loads(factory.verify_market_cap(price=100, shares=1e9, reported_cap=2e11))
        assert data["passed"] is False
        assert data["deviation_pct"] == pytest.approx(50.0)


class TestGetFinancials:
    def test_a_share_uses_structured_eastmoney_feed(self, factory):
        factory.data_hub._sources = {"eastmoney": types.SimpleNamespace(available=True)}
        factory.data_hub.fetch.return_value = types.SimpleNamespace(
            data={"ticker": "600519", "periods": [{"report_date": "2025-12-31", "revenue": 1.7e11}]}
        )

        data = json.loads(factory.get_financials("600519"))

        assert data["periods"][0]["revenue"] == 1.7e11
        assert "cross_validate_metric" in data["cross_validate_hint"]

    def test_non_a_share_returns_source_priority_table(self, factory):
        data = json.loads(factory.get_financials("NVDA"))

        assert data["periods"] == []
        assert data["structured_source"] is None
        assert "美股" in data["source_priority"]
        assert "SEC EDGAR" in data["source_priority"]["美股"]["primary_disclosure"]

    def test_empty_ticker_is_rejected(self, factory):
        assert "error" in json.loads(factory.get_financials("  "))

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
    def test_get_tools_returns_20(self, factory):
        """get_tools 返回当前公开的 19 个工具函数。"""
        tools = factory.get_tools()
        assert len(tools) == 20
        # 所有条目都是 callable
        for tool in tools:
            assert callable(tool)

    def test_get_tools_names(self, factory):
        """工具函数名称正确。"""
        tools = factory.get_tools()
        names = [t.__name__ if hasattr(t, '__name__') else t.__func__.__name__ for t in tools]
        expected = [
            "search_web", "read_file", "list_dir", "write_to_file",
            "get_realtime_quote", "cross_validate_price", "cross_validate_metric",
            "verify_market_cap", "get_financials", "check_report_quality",
            "get_evidence_log",
            "get_portfolio_snapshot", "preview_trade", "execute_trade",
            "execute_python_script", "browser_fetch", "drill_source",
            "browser_operate", "system_doctor", "learn_source",
        ]
        assert names == expected


# ---- 取证预算（v5.0） ----

from core.toolbus.budget import BudgetManager  # noqa: E402


@pytest.fixture
def budgeted_factory(tmp_path):
    """带 2 点取证预算的 ToolFactory。"""
    data_mgr = MagicMock()
    data_mgr.search_web.return_value = "search result"
    data_hub = MagicMock()
    data_hub._sources = {}
    f = ToolFactory(
        data_mgr=data_mgr,
        data_hub=data_hub,
        ledger=MagicMock(),
        kill_switch=MagicMock(),
        guard_chain=MagicMock(),
        execution_pipeline=MagicMock(),
        project_root=str(tmp_path),
        budget=BudgetManager(max_budget=2),
        workflow_name="quick",
    )
    return f


class TestSearchBudget:
    def test_calls_within_budget_succeed(self, budgeted_factory):
        assert "search result" in budgeted_factory.search_web("q1")
        assert "search result" in budgeted_factory.search_web("q2")

    def test_call_beyond_budget_is_refused_softly(self, budgeted_factory):
        budgeted_factory.search_web("q1")
        budgeted_factory.search_web("q2")
        third = budgeted_factory.search_web("q3")

        # 软失败：返回指令而不是抛异常，避免整轮工具循环作废
        assert "取证预算已用尽" in third
        assert "UNSOURCED" in third
        assert budgeted_factory.data_mgr.search_web.call_count == 2

    def test_low_balance_footer_nudges_model(self, budgeted_factory):
        first = budgeted_factory.search_web("q1")
        assert "取证预算余额: 1" in first

    def test_no_budget_means_unlimited(self, factory):
        factory.data_mgr.search_web.return_value = "ok"
        for _ in range(5):
            assert "取证预算已用尽" not in factory.search_web("q")

    def test_non_fetching_tools_are_free(self, budgeted_factory, tmp_path):
        (tmp_path / "note.md").write_text("hello", encoding="utf-8")
        for _ in range(5):
            budgeted_factory.read_file("note.md")
        # 读文件不产生外部请求，不该占用取证预算
        assert budgeted_factory.budget.remaining() == 2

    def test_browser_fetch_fallback_does_not_double_charge(self, budgeted_factory):
        budgeted_factory.data_hub.fetch.side_effect = RuntimeError("engine down")
        budgeted_factory.browser_fetch(site="xueqiu", command="search", query="NVDA")
        # 一次外部请求只扣一次费，哪怕内部从结构化抓取降级到了网页搜索
        assert budgeted_factory.budget.remaining() == 1


class TestReportTierInference:
    def test_tier_and_ticker_from_filename(self, factory):
        assert factory._infer_report_context("Reports/deepdive/20260604_NVDA_Deep.md") == (
            "deep",
            "NVDA",
        )
        assert factory._infer_report_context("Reports/20260604/20260604_Market_Scan.md") == (
            "scan",
            "",
        )
        assert factory._infer_report_context("Reports/20260604/odd-name.md") == ("default", "")

    def test_quality_gate_blocks_write_and_explains(self, factory, tmp_path):
        result = factory.write_to_file(
            "Reports/20260604/20260604_NVDA_Quick.md", "# 只有标题没有内容"
        )
        assert "Report quality gate failed" in result
        assert "重新调用 write_to_file" in result
        assert not (tmp_path / "Reports" / "20260604" / "20260604_NVDA_Quick.md").exists()

    def test_check_report_quality_uses_filename_tier(self, factory):
        thin = "# 报告\n\n## 结论先行\n结论：等待。\n"
        as_default = json.loads(factory.check_report_quality(thin))
        as_deep = json.loads(
            factory.check_report_quality(thin, filename="Reports/deepdive/20260604_NVDA_Deep.md")
        )
        assert as_default["tier"] == "default"
        assert as_deep["tier"] == "deep"


class TestSegmentedReportWrite:
    """分段写入必须校验拼接后的完整文件，而不是单个片段。"""

    _VALID = """# 20260604 NVDA 报告

## 结论先行
结论：等待。置信度：中。

## 实时数据快照
- NVDA price: 100.0, source: yfinance, fetched_at: 2026-06-04T12:00:00Z

## 证据台账
| 判断 | 证据 | 来源 | 日期 |
| --- | --- | --- | --- |
| 看空：增长放缓 | 指引下修 | source: test | 2026-06-04 |
| 估值偏高 | PE 高于中位 | source: test | 2026-06-04 |

## Bull/Base/Bear
- Bull (25%): 数据中心订单超预期，EPS 上修，估值维持高位不回落。
- Base (55%): 增长按指引兑现，估值随盈利消化，股价区间震荡。
- Bear (20%): 客户资本开支放缓，指引下修，估值与盈利双杀。

## 行动计划
- 触发器：回落至 90 元以下且季度指引未下修时重新评估建仓。
- 失效条件：连续两个季度数据中心收入环比负增长，则本轮逻辑作废。
- 下次复盘：下一季财报发布后三个交易日内。

## 风险与不确定性
- 数据源可能延迟，季度指引口径存在 GAAP / Non-GAAP 差异，需要回原始披露复核。

### 证据缺口
- 缺分部毛利率拆分 — 影响估值锚点 — 下一步去 10-Q 原文取。

## 质量自检
- 已检查来源、日期、反方观点和行动计划。
"""

    def test_append_is_checked_against_combined_file(self, factory, tmp_path):
        path = "Reports/20260604/20260604_NVDA_Quick.md"
        assert "Successfully saved" in factory.write_to_file(path, self._VALID)

        # 追加片段本身不是完整报告，但拼接后的文件仍然合格
        result = factory.write_to_file(path, "\n## 冲突解释\n与上一份的差异来自更新后证据。\n", mode="a")

        assert "Successfully appended" in result
        written = (tmp_path / path).read_text(encoding="utf-8")
        assert "## 冲突解释" in written
        assert written.startswith("# 20260604")

    def test_append_that_breaks_the_report_is_still_rejected(self, factory, tmp_path):
        path = "Reports/20260604/20260604_NVDA_Quick.md"
        factory.write_to_file(path, self._VALID)
        # 拼接后仍要过门禁：这里用一个会让 ticker 对不上的全新片段是无效的，
        # 改为验证向不存在的报告直接追加片段会被拒（拼接后 = 片段本身）
        result = factory.write_to_file(
            "Reports/20260604/20260604_TSLA_Quick.md", "## 补充\n只有一个片段。\n", mode="a"
        )
        assert "Report quality gate failed" in result


# ---- 证据链（v5.0） ----

from core.toolbus.evidence import EvidenceRecorder  # noqa: E402


@pytest.fixture
def recording_factory(tmp_path):
    """带证据链记录的 ToolFactory。"""
    data_mgr = MagicMock()
    data_mgr.search_web.return_value = "search result body"
    data_hub = MagicMock()
    data_hub._sources = {}
    return ToolFactory(
        data_mgr=data_mgr,
        data_hub=data_hub,
        ledger=MagicMock(),
        kill_switch=MagicMock(),
        guard_chain=MagicMock(),
        execution_pipeline=MagicMock(),
        project_root=str(tmp_path),
        workflow_name="quick",
        evidence=EvidenceRecorder(),
    )


class TestEvidenceRecording:
    def test_search_is_recorded(self, recording_factory):
        recording_factory.search_web("NVDA earnings")

        assert len(recording_factory.evidence.sources) == 1
        ref = recording_factory.evidence.sources[0]
        assert ref.tool_name == "search_web"
        assert ref.query == "NVDA earnings"
        assert "search result body" in ref.snippet
        assert ref.timestamp is not None

    def test_quote_tools_are_recorded_even_though_they_are_free(self, recording_factory):
        recording_factory.data_mgr.fetch_market_prices.return_value = [
            {"ticker": "NVDA", "name": "NVDA", "price": 100.0, "change": 1.0}
        ]
        recording_factory.get_realtime_quote("NVDA")

        # 取行情不消耗预算，但它确实是一次真实取证，必须进证据链
        names = [r.tool_name for r in recording_factory.evidence.sources]
        assert "get_realtime_quote" in names

    def test_refused_call_is_not_recorded(self, tmp_path):
        factory = ToolFactory(
            data_mgr=MagicMock(), data_hub=MagicMock(), ledger=MagicMock(),
            kill_switch=MagicMock(), guard_chain=MagicMock(),
            execution_pipeline=MagicMock(), project_root=str(tmp_path),
            budget=BudgetManager(max_budget=0), evidence=EvidenceRecorder(),
        )
        factory.data_hub._sources = {}

        result = factory.search_web("blocked")

        assert "取证预算已用尽" in result
        assert factory.evidence.sources == []

    def test_get_evidence_log_returns_what_was_fetched(self, recording_factory):
        recording_factory.search_web("q1")
        recording_factory.search_web("q2")

        payload = json.loads(recording_factory.get_evidence_log())

        assert payload["count"] == 2
        assert [r["query"] for r in payload["records"]] == ["q1", "q2"]

    def test_evidence_log_is_empty_without_recorder(self, factory):
        payload = json.loads(factory.get_evidence_log())
        assert payload["records"] == []


class TestLiveToolingGateUsesRealRecord:
    """门禁此前只对正文做正则匹配——写下 fetched_at 三个字就能骗过。"""

    _REPORT = """# 20260604 NVDA 报告

## 结论先行
结论：等待。置信度：中。

## 实时数据快照
- NVDA 现价 100.0，日内涨跌 +1.2%，取自行情接口

## 证据台账
| 判断 | 证据 | 来源 | 日期 |
| --- | --- | --- | --- |
| 看空：增长放缓 | 下季指引低于市场一致预期 | 来源: 公司电话会纪要 | 2026-06-04 |
| 估值偏高 | Forward PE 高于近五年中位数 | 来源: 财务数据库 | 2026-06-04 |
| 订单能见度下降 | 主要客户资本开支指引下修 | 来源: 客户季报 | 2026-06-03 |

## Bull/Base/Bear
- Bull (25%): 数据中心订单超预期，EPS 上修，估值维持高位不回落。
- Base (55%): 增长按指引兑现，估值随盈利消化，股价区间震荡。
- Bear (20%): 客户资本开支放缓，指引下修，估值与盈利双杀。

## 行动计划
- 触发器：回落至 90 元以下且季度指引未下修时重新评估建仓。
- 失效条件：连续两个季度数据中心收入环比负增长，则本轮逻辑作废。
- 下次复盘：下一季财报发布后三个交易日内。

## 风险与不确定性
- 口径存在 GAAP / Non-GAAP 差异，需要回原始披露复核；行情数据可能延迟。

### 证据缺口
- 缺分部毛利率拆分 — 影响估值锚点 — 下一步去 10-Q 原文取。

## 质量自检
- 已检查来源、日期、反方观点和行动计划。
"""

    def _factory(self, tmp_path, recorder):
        f = ToolFactory(
            data_mgr=MagicMock(), data_hub=MagicMock(), ledger=MagicMock(),
            kill_switch=MagicMock(), guard_chain=MagicMock(),
            execution_pipeline=MagicMock(), project_root=str(tmp_path),
            workflow_name="quick", evidence=recorder,
        )
        f.data_hub._sources = {}
        return f

    def test_zero_real_fetches_is_rejected_however_the_text_reads(self, tmp_path):
        factory = self._factory(tmp_path, EvidenceRecorder())
        # 正文里写满 fetched_at 也没用——工具层记录为 0
        text = self._REPORT.replace("- NVDA 现价 100.0", "- NVDA 100.0 fetched_at: 2026-06-04T12:00:00Z")

        result = factory.write_to_file("Reports/20260604/20260604_NVDA_Quick.md", text)

        assert "Report quality gate failed" in result
        assert "missing_live_tooling_evidence" in result

    def test_real_fetch_satisfies_the_gate_without_magic_words(self, tmp_path):
        recorder = EvidenceRecorder()
        factory = self._factory(tmp_path, recorder)
        factory.data_mgr.search_web.return_value = "real result"
        factory.search_web("NVDA guidance")

        # 报告正文没有 fetched_at / verdict 之类的字样，但确实取过数
        result = factory.write_to_file("Reports/20260604/20260604_NVDA_Quick.md", self._REPORT)

        assert "Successfully saved" in result

    def test_evidence_log_is_saved_next_to_the_report(self, tmp_path):
        recorder = EvidenceRecorder()
        factory = self._factory(tmp_path, recorder)
        factory.data_mgr.search_web.return_value = "real result"
        factory.search_web("NVDA guidance")

        factory.write_to_file("Reports/20260604/20260604_NVDA_Quick.md", self._REPORT)

        log = tmp_path / "Reports" / "20260604" / "evidence" / "20260604_NVDA_Quick_sources.jsonl"
        assert log.is_file()
        record = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[0])
        assert record["tool_name"] == "search_web"
        assert record["query"] == "NVDA guidance"

    def test_gate_is_unchanged_when_recording_is_off(self, tmp_path):
        factory = self._factory(tmp_path, None)
        result = factory.write_to_file("Reports/20260604/20260604_NVDA_Quick.md", self._REPORT)
        # 没有记录器时退回正文正则判断：这份报告没有 fetched_at 痕迹
        assert "missing_live_tooling_evidence" in result
