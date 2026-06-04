"""Report quality gate for LLM-generated research reports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class SectionRule:
    key: str
    labels: tuple[str, ...]
    required_terms: tuple[str, ...] = field(default_factory=tuple)


class ReportQualityChecker:
    """Validate report structure, evidence hygiene, and unexplained contradictions."""

    SECTION_RULES = (
        SectionRule("conclusion", ("结论先行", "缁撹鍏堣", "Executive Summary", "Conclusion", "Decision")),
        SectionRule("market_data", ("实时数据快照", "瀹炴椂鏁版嵁蹇収", "Data Snapshot", "Market Data", "Quote Snapshot")),
        SectionRule("evidence", ("证据台账", "璇佹嵁鍙拌处", "Evidence Ledger", "Evidence Table", "Sources")),
        SectionRule("scenario", ("Bull/Base/Bear", "Bull Bear Base", "情景分析", "鎯呮櫙鍒嗘瀽", "多空", "澶氱┖")),
        SectionRule("action_plan", ("行动计划", "琛屽姩璁″垝", "Action Plan", "Triggers", "触发器")),
        SectionRule("risk", ("风险与不确定性", "椋庨櫓涓庝笉纭畾鎬", "Risks", "Uncertainty", "Pre-Mortem")),
        SectionRule("quality_gate", ("质量自检", "璐ㄩ噺鑷", "Quality Gate", "Self Check", "QA")),
    )

    DATE_PATTERN = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|20\d{6})\b")
    SOURCE_PATTERN = re.compile(r"(https?://|source\s*:|来源|鏉ユ簮|出处|鍑哄|fetched_at)", re.IGNORECASE)

    BULLISH_TERMS = ("买入", "逢低买入", "积极持有", "看多", "Bullish", "加仓")
    REJECT_TERMS = ("驳回", "Reject", "拒绝买入", "不买入", "无买入动作", "禁止买入")
    TUNGSTEN_UP_TERMS = ("钨价持续飙升", "钨价上涨", "连涨", "飙升", "走强", "突破", "创新高")
    TUNGSTEN_DOWN_TERMS = ("钨价下跌", "钨价回落", "腰斩", "崩塌", "暴跌", "跌破", "高位调整")
    CONFLICT_EXPLANATION_TERMS = ("冲突解释", "差异解释", "与历史报告差异", "与前次报告差异", "口径变化", "更新后证据")

    def check(self, markdown: str, prior_reports: Iterable[dict] | None = None) -> dict:
        text = markdown or ""
        missing_sections = [
            rule.key
            for rule in self.SECTION_RULES
            if not any(label.lower() in text.lower() for label in rule.labels)
        ]

        issues = []
        if not text.lstrip().startswith("#"):
            issues.append("missing_top_level_title")
        if len(text.strip()) < 300:
            issues.append("report_too_short")
        if not self.DATE_PATTERN.search(text):
            issues.append("missing_explicit_date")
        if not self.SOURCE_PATTERN.search(text):
            issues.append("missing_source_reference")
        if ("Bull" not in text and "多" not in text and "澶" not in text) or (
            "Bear" not in text and "空" not in text and "绌" not in text
        ):
            issues.append("missing_two_sided_view")

        conflict_details = self._find_prior_report_conflicts(text, prior_reports or [])
        if conflict_details and not self._has_conflict_explanation(text):
            issues.append("unexplained_conflict_with_prior_report")

        return {
            "passed": not missing_sections and not issues,
            "missing_sections": missing_sections,
            "issues": issues,
            "conflict_details": conflict_details,
        }

    def _find_prior_report_conflicts(self, current: str, prior_reports: Iterable[dict]) -> list[dict]:
        current_stance = self._stance(current)
        current_tungsten = self._tungsten_direction(current)
        conflicts = []

        for report in prior_reports:
            prior_text = report.get("content", "") if isinstance(report, dict) else str(report)
            prior_stance = self._stance(prior_text)
            prior_tungsten = self._tungsten_direction(prior_text)

            reasons = []
            if {current_stance, prior_stance} == {"bullish", "reject"}:
                reasons.append("action_reversal")
            if {current_tungsten, prior_tungsten} == {"up", "down"}:
                reasons.append("tungsten_price_direction_reversal")

            if reasons:
                conflicts.append({
                    "path": report.get("path", "") if isinstance(report, dict) else "",
                    "reasons": reasons,
                    "prior_stance": prior_stance,
                    "current_stance": current_stance,
                    "prior_tungsten_direction": prior_tungsten,
                    "current_tungsten_direction": current_tungsten,
                })

        return conflicts

    def _stance(self, text: str) -> str:
        if any(term in text for term in self.REJECT_TERMS):
            return "reject"
        if any(term in text for term in self.BULLISH_TERMS):
            return "bullish"
        return "neutral"

    def _tungsten_direction(self, text: str) -> str:
        if "钨" not in text and "黑钨" not in text:
            return "unknown"
        if any(term in text for term in self.TUNGSTEN_DOWN_TERMS):
            return "down"
        if any(term in text for term in self.TUNGSTEN_UP_TERMS):
            return "up"
        return "unknown"

    def _has_conflict_explanation(self, text: str) -> bool:
        return any(term in text for term in self.CONFLICT_EXPLANATION_TERMS)
