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


# --- 分档与实质校验（v5.0 门禁升级） ---------------------------------------


def _report(
    *,
    evidence_rows: int = 6,
    bear_row: bool = True,
    self_check_rows: int | None = None,
    extra: str = "",
    risk_body: str = "- 数据源可能延迟，需要复核。",
) -> str:
    rows = []
    for i in range(evidence_rows):
        judgement = "看空：增长放缓" if (bear_row and i == 0) else f"判断{i}"
        rows.append(f"| {judgement} | 证据{i} | source: test | 2026-06-04 | T1 |")
    table = "\n".join(rows)
    self_check_line = (
        f"- 证据台账行数: {self_check_rows}\n- 联网取证次数: 4\n"
        if self_check_rows is not None
        else "- 已检查来源、日期、反方观点和行动计划。\n"
    )
    return f"""# 20260604 NVDA 报告

## 结论先行
结论：等待。置信度：中。{extra}

## 实时数据快照
- NVDA price: 100.0, source: yfinance, fetched_at: 2026-06-04T12:00:00Z
- verdict: 跨族交叉验证通过，consensus_price 100.0

## 证据台账
| 判断 | 证据 | 来源 | 日期 | 等级 |
| --- | --- | --- | --- | --- |
{table}

## Bull/Base/Bear
- Bull: EPS 上修。
- Base: 估值消化。
- Bear: 增长放缓。

## 行动计划
等待回落到行动价后再评估。

## 风险与不确定性
{risk_body}

## 质量自检
{self_check_line}"""


class TestTieredThresholds:
    def test_deep_tier_rejects_thin_report(self):
        result = ReportQualityChecker().check(_report(), tier="deep")
        assert result["tier"] == "deep"
        assert "report_below_tier_minimum" in result["issues"]

    def test_quick_tier_accepts_same_report(self):
        result = ReportQualityChecker().check(_report(), tier="quick")
        assert result["passed"] is True

    def test_evidence_rows_below_tier_minimum_is_flagged(self):
        result = ReportQualityChecker().check(_report(evidence_rows=2), tier="decision")
        assert "evidence_rows_below_tier_minimum" in result["issues"]

    def test_unknown_tier_falls_back_to_default(self):
        assert ReportQualityChecker().check(_report(), tier="nonsense")["tier"] == "default"


class TestEvidenceLedgerSubstance:
    def test_section_present_but_table_empty_is_rejected(self):
        """有『证据台账』这四个字不等于有证据——旧门禁只查标题，这里查数据行。"""
        result = ReportQualityChecker().check(_report(evidence_rows=0), tier="quick")
        assert "evidence_table_has_no_rows" in result["issues"]
        assert result["evidence_row_count"] == 0

    def test_row_count_is_reported(self):
        result = ReportQualityChecker().check(_report(evidence_rows=6), tier="quick")
        assert result["evidence_row_count"] == 6

    def test_missing_bear_row_is_flagged_for_workflow_tiers(self):
        result = ReportQualityChecker().check(_report(bear_row=False), tier="quick")
        assert "evidence_missing_bear_row" in result["issues"]

    def test_missing_bear_row_is_tolerated_on_default_tier(self):
        result = ReportQualityChecker().check(_report(bear_row=False), tier="default")
        assert "evidence_missing_bear_row" not in result["issues"]


class TestEmptySections:
    def test_placeholder_body_counts_as_empty(self):
        result = ReportQualityChecker().check(_report(risk_body="TBD"), tier="quick")
        assert "empty_sections" in result["issues"]
        assert "risk" in result["thin_sections"]

    def test_real_one_liner_is_accepted(self):
        result = ReportQualityChecker().check(_report(risk_body="- 数据源延迟。"), tier="quick")
        assert "risk" not in result["thin_sections"]


class TestSelfCheckCounts:
    def test_deep_tier_requires_declared_counts(self):
        result = ReportQualityChecker().check(_report(), tier="deep")
        assert "self_check_counts_missing" in result["issues"]

    def test_declared_count_must_match_actual_rows(self):
        result = ReportQualityChecker().check(
            _report(evidence_rows=6, self_check_rows=12), tier="quick"
        )
        assert "self_check_count_mismatch" in result["issues"]

    def test_matching_count_passes(self):
        result = ReportQualityChecker().check(
            _report(evidence_rows=6, self_check_rows=6), tier="quick"
        )
        assert "self_check_count_mismatch" not in result["issues"]
        assert result["self_check"]["evidence_rows"] == 6


class TestPriceProvenance:
    def test_target_price_without_cross_validation_is_rejected(self):
        report = _report(extra=" 目标价 130 元。").replace(
            "- verdict: 跨族交叉验证通过，consensus_price 100.0", "- 现价 100.0"
        )
        result = ReportQualityChecker().check(report, tier="quick")
        assert "price_commitment_without_provenance" in result["issues"]

    def test_target_price_with_verdict_line_passes(self):
        result = ReportQualityChecker().check(_report(extra=" 目标价 130 元。"), tier="quick")
        assert "price_commitment_without_provenance" not in result["issues"]


class TestLiveToolingAndTicker:
    def test_report_without_tooling_traces_is_rejected(self):
        report = _report().replace("fetched_at: 2026-06-04T12:00:00Z", "今天").replace(
            "- verdict: 跨族交叉验证通过，consensus_price 100.0", "- 现价 100.0"
        )
        result = ReportQualityChecker().check(report, tier="quick")
        assert "missing_live_tooling_evidence" in result["issues"]

    def test_ticker_mismatch_is_detected(self):
        result = ReportQualityChecker().check(_report(), tier="quick", expected_ticker="TSLA")
        assert "ticker_mismatch" in result["issues"]

    def test_bare_code_matches_suffixed_ticker(self):
        report = _report().replace("NVDA", "000657")
        result = ReportQualityChecker().check(report, tier="quick", expected_ticker="000657.SZ")
        assert "ticker_mismatch" not in result["issues"]


class TestDirectionRulesTable:
    def test_direction_reversal_uses_rule_table_not_hardcoding(self):
        from core.report_quality import DirectionRule

        checker = ReportQualityChecker()
        # 规则以数据形式存在，是「加一行」而不是「改逻辑」
        assert all(isinstance(rule, DirectionRule) for rule in checker.DIRECTION_RULES)
        assert {r.name for r in checker.DIRECTION_RULES} == {"tungsten_price"}

    def test_directions_report_unknown_when_subject_absent(self):
        checker = ReportQualityChecker()
        assert checker._directions("完全无关的报告")["tungsten_price"] == "unknown"
