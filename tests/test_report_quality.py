import json

from core.report_quality import ReportQualityChecker


def test_thin_report_fails_required_sections():
    result = ReportQualityChecker().check("thin report")

    assert result["passed"] is False
    assert "conclusion" in result["missing_sections"]
    assert "evidence" in result["missing_sections"]
    assert "market_data" in result["missing_sections"]


def test_report_with_required_sections_sources_and_dates_passes():
    report = """# NVDA Decision Audit

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

    result = ReportQualityChecker().check(report)

    assert result["passed"] is True
    assert result["missing_sections"] == []
    assert result["issues"] == []


def test_json_serializable_result_shape():
    result = ReportQualityChecker().check("thin report")

    encoded = json.dumps(result, ensure_ascii=False)

    assert "missing_sections" in encoded


def _valid_chinese_report(conclusion: str) -> str:
    return f"""# 20260604 中钨高新报告

## 结论先行
{conclusion}

## 实时数据快照
- 000657.SZ price: 74.0, source: yfinance, fetched_at: 2026-06-04T12:00:00Z

## 证据台账
| 判断 | 证据 | 来源 | 日期 |
| --- | --- | --- | --- |
| 钨价方向 | 黑钨精矿价格变化 | source: test | 2026-06-04 |

## Bull/Base/Bear
- Bull: 钨价继续上涨。
- Base: 钨价震荡。
- Bear: 钨价下跌。

## 行动计划
根据触发器分批执行。

## 风险与不确定性
- 数据源存在延迟，需要复核。

## 质量自检
- 已检查来源、日期、反方观点和行动计划。
"""


def test_normal_chinese_sections_are_recognized():
    result = ReportQualityChecker().check(_valid_chinese_report("结论：等待。置信度：中。"))

    assert result["passed"] is True


def test_conflicting_prior_report_requires_explanation():
    prior = _valid_chinese_report("结论：逢低买入。钨价持续飙升，黑钨精矿连涨。")
    current = _valid_chinese_report("结论：驳回。钨价腰斩下跌，黑钨精矿崩塌。")

    result = ReportQualityChecker().check(current, prior_reports=[{"path": "quick.md", "content": prior}])

    assert result["passed"] is False
    assert "unexplained_conflict_with_prior_report" in result["issues"]


def test_conflicting_prior_report_passes_when_explained():
    prior = _valid_chinese_report("结论：逢低买入。钨价持续飙升，黑钨精矿连涨。")
    current = _valid_chinese_report(
        "结论：驳回。钨价腰斩下跌，黑钨精矿崩塌。\n\n"
        "## 冲突解释\n"
        "与 quick.md 的差异来自更新后的 SMM 价格数据，钨价方向由上涨转为下跌。"
    )

    result = ReportQualityChecker().check(current, prior_reports=[{"path": "quick.md", "content": prior}])

    assert result["passed"] is True
