"""Report quality gate for LLM-generated research reports.

设计原则：**只校验能判真假的东西**。
「护城河分析是否深刻」不是这里的事；「证据台账有没有数据行」「给了目标价却没有
价格交叉验证记录」「自检里报的行数与正文实际行数对不对得上」是这里的事。

分档校验（tier）：一份 /quick 事件快评和一份 /deep 建档报告不该共用同一条下限。
tier 由调用方按文件名推断，未知时退回宽松的 default 档，保证历史报告与
自由对话产出的 Markdown 不被误杀。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class SectionRule:
    key: str
    labels: tuple[str, ...]
    # 章节标题下方的正文最少字符数。阈值刻意压得很低：目的是抓「只有标题没有内容」
    # 和「TBD / 待补充 / N/A」这类占位，而不是给正常的一行结论判死刑。
    min_body_chars: int = 6
    required_terms: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TierProfile:
    """各档报告的阈值。深研要求高，快评要求低，但没有一档可以零证据。"""

    name: str
    min_chars: int
    min_evidence_rows: int
    require_self_check_counts: bool = False
    # 证据台账里必须至少有一行是反方证据。只对 workflow 产出的报告强制——
    # 来源未知的历史报告与自由对话产出走 default 档，不因此被拒绝落盘。
    require_bear_row: bool = True


@dataclass(frozen=True)
class DirectionRule:
    """价格/指标方向反转的检测规则。

    此前「钨价方向」是硬编码在校验器里的个例；现在它只是这张表里的一行，
    新增一个跟踪标的等于加一条数据，不用改逻辑。
    """

    name: str
    subject_terms: tuple[str, ...]
    up_terms: tuple[str, ...]
    down_terms: tuple[str, ...]


class ReportQualityChecker:
    """Validate report structure, evidence hygiene, and unexplained contradictions."""

    # 历史遗留：早期报告在 GBK/UTF-8 双解码下写入过乱码标题。
    # 编码问题已在写入侧修复，这里保留识别能力只为让旧报告仍可被解析，
    # 不再向新规则中扩散——新增章节一律只写正常文本。
    _LEGACY_MOJIBAKE_LABELS = {
        "conclusion": ("缁撹鍏堣",),
        "market_data": ("瀹炴椂鏁版嵁蹇収",),
        "evidence": ("璇佹嵁鍙拌处",),
        "scenario": ("鎯呮櫙鍒嗘瀽", "澶氱┖"),
        "action_plan": ("琛屽姩璁″垝",),
        "risk": ("椋庨櫓涓庝笉纭畾鎬",),
        "quality_gate": ("璐ㄩ噺鑷",),
    }

    SECTION_RULES = (
        SectionRule("conclusion", ("结论先行", "Executive Summary", "Conclusion", "Decision")),
        SectionRule("market_data", ("实时数据快照", "Data Snapshot", "Market Data", "Quote Snapshot")),
        SectionRule("evidence", ("证据台账", "Evidence Ledger", "Evidence Table", "Sources")),
        SectionRule("scenario", ("Bull/Base/Bear", "Bull Bear Base", "情景分析", "多空")),
        SectionRule("action_plan", ("行动计划", "Action Plan", "Triggers", "触发器")),
        SectionRule("risk", ("风险与不确定性", "Risks", "Uncertainty", "Pre-Mortem")),
        SectionRule("quality_gate", ("质量自检", "Quality Gate", "Self Check", "QA")),
    )

    TIERS = {
        # 深研建档：篇幅与证据密度都最高，且必须在自检里报出可核对的计数
        "deep": TierProfile("deep", min_chars=4000, min_evidence_rows=6, require_self_check_counts=True),
        # 决策类：篇幅可以不长，但触碰真金白银，证据密度不能低
        "decision": TierProfile("decision", min_chars=2000, min_evidence_rows=5, require_self_check_counts=True),
        # 扫描类：广度优先，单标的深度有限
        "scan": TierProfile("scan", min_chars=1500, min_evidence_rows=3),
        # 快评：24 小时内的事件反应，允许薄，但仍需两条以上证据
        "quick": TierProfile("quick", min_chars=600, min_evidence_rows=2),
        # 未知来源（历史报告、自由对话产出）：只守最低底线
        "default": TierProfile(
            "default", min_chars=300, min_evidence_rows=1,
            require_bear_row=False,
        ),
    }

    # 文件名 → 档位。tool_factory 按报告文件名推断后传入。
    WORKFLOW_TIERS = {
        "deep": "deep", "value": "deep",
        "buy": "decision", "sell": "decision", "option": "decision", "optimize": "decision",
        "scan": "scan", "lead": "scan", "theme": "scan", "core": "scan",
        "position": "scan", "macro": "scan",
        "quick": "quick", "update": "quick", "verify": "quick", "rethink": "quick",
    }

    DATE_PATTERN = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|20\d{6})\b")
    SOURCE_PATTERN = re.compile(r"(https?://|source\s*:|来源|出处|fetched_at)", re.IGNORECASE)
    # 实际调用过取证工具会留下这些痕迹；整轮零取证的报告不该落盘
    LIVE_TOOLING_PATTERN = re.compile(
        r"(fetched_at|verdict|cross_validate|consensus_price|source_method)", re.IGNORECASE
    )
    # 给出这些数字等于在给可执行的交易指令，必须有价格交叉验证背书
    PRICE_COMMITMENT_PATTERN = re.compile(r"(目标价|止损价|止损位|盈亏比|Target Price|Stop Loss)")
    # cross_validate_price 的 verdict 会被逐字抄进报告
    PRICE_PROVENANCE_PATTERN = re.compile(
        r"(verdict|交叉验证|跨族|单源|consensus_price)", re.IGNORECASE
    )
    MARKDOWN_ROW_PATTERN = re.compile(r"^\s*\|.+\|\s*$")
    SEPARATOR_ROW_PATTERN = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
    HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s")

    BEAR_TERMS = ("bear", "看空", "空方", "反方", "利空", "下行")
    UNSOURCED_MARK = "[UNSOURCED]"

    # 自检里要求填写的计数，格式如「证据台账行数: 7」
    SELF_CHECK_PATTERNS = {
        "evidence_rows": re.compile(r"证据台账行数\s*[:：]\s*(\d+)"),
        "search_calls": re.compile(r"联网取证次数\s*[:：]\s*(\d+)"),
    }

    BULLISH_TERMS = ("买入", "逢低买入", "积极持有", "看多", "Bullish", "加仓")
    REJECT_TERMS = ("驳回", "Reject", "拒绝买入", "不买入", "无买入动作", "禁止买入")
    CONFLICT_EXPLANATION_TERMS = (
        "冲突解释", "差异解释", "与历史报告差异", "与前次报告差异", "口径变化", "更新后证据",
    )

    DIRECTION_RULES = (
        DirectionRule(
            name="tungsten_price",
            subject_terms=("钨", "黑钨"),
            up_terms=("钨价持续飙升", "钨价上涨", "连涨", "飙升", "走强", "突破", "创新高"),
            down_terms=("钨价下跌", "钨价回落", "腰斩", "崩塌", "暴跌", "跌破", "高位调整"),
        ),
    )

    def check(
        self,
        markdown: str,
        prior_reports: Iterable[dict] | None = None,
        tier: str = "default",
        expected_ticker: str = "",
    ) -> dict:
        text = markdown or ""
        profile = self.TIERS.get((tier or "default").lower(), self.TIERS["default"])
        lowered = text.lower()

        missing_sections = []
        thin_sections = []
        for rule in self.SECTION_RULES:
            labels = rule.labels + self._LEGACY_MOJIBAKE_LABELS.get(rule.key, ())
            matched_label = next((lb for lb in labels if lb.lower() in lowered), None)
            if matched_label is None:
                missing_sections.append(rule.key)
                continue
            if len(self._section_body(text, matched_label)) < rule.min_body_chars:
                thin_sections.append(rule.key)

        issues: list[str] = []
        if not text.lstrip().startswith("#"):
            issues.append("missing_top_level_title")
        if len(text.strip()) < profile.min_chars:
            issues.append("report_below_tier_minimum")
        if not self.DATE_PATTERN.search(text):
            issues.append("missing_explicit_date")
        if not self.SOURCE_PATTERN.search(text):
            issues.append("missing_source_reference")
        if ("Bull" not in text and "多" not in text) or ("Bear" not in text and "空" not in text):
            issues.append("missing_two_sided_view")
        if thin_sections:
            issues.append("empty_sections")

        evidence_rows = self._evidence_rows(text)
        if "evidence" not in missing_sections:
            if not evidence_rows:
                issues.append("evidence_table_has_no_rows")
            elif len(evidence_rows) < profile.min_evidence_rows:
                issues.append("evidence_rows_below_tier_minimum")
            if profile.require_bear_row and evidence_rows and not self._has_bear_row(evidence_rows):
                issues.append("evidence_missing_bear_row")

        if not self.LIVE_TOOLING_PATTERN.search(text):
            issues.append("missing_live_tooling_evidence")

        if self.PRICE_COMMITMENT_PATTERN.search(text) and not self.PRICE_PROVENANCE_PATTERN.search(text):
            issues.append("price_commitment_without_provenance")

        if expected_ticker and not self._mentions_ticker(text, expected_ticker):
            issues.append("ticker_mismatch")

        self_check = self._self_check_counts(text)
        if profile.require_self_check_counts:
            missing_counts = [k for k in self.SELF_CHECK_PATTERNS if self_check.get(k) is None]
            if missing_counts:
                issues.append("self_check_counts_missing")
        declared_rows = self_check.get("evidence_rows")
        if declared_rows is not None and declared_rows != len(evidence_rows):
            issues.append("self_check_count_mismatch")

        conflict_details = self._find_prior_report_conflicts(text, prior_reports or [])
        if conflict_details and not self._has_conflict_explanation(text):
            issues.append("unexplained_conflict_with_prior_report")

        return {
            "passed": not missing_sections and not issues,
            "tier": profile.name,
            "missing_sections": missing_sections,
            "thin_sections": thin_sections,
            "issues": issues,
            "evidence_row_count": len(evidence_rows),
            "unsourced_claims": text.count(self.UNSOURCED_MARK),
            "self_check": self_check,
            "conflict_details": conflict_details,
        }

    # --- section / table parsing -------------------------------------------------

    def _section_body(self, text: str, label: str) -> str:
        """返回某个章节标题之后、下一个标题之前的正文。"""
        lines = text.splitlines()
        body: list[str] = []
        collecting = False
        for line in lines:
            if collecting:
                if self.HEADING_PATTERN.match(line):
                    break
                body.append(line.strip())
                continue
            if label.lower() in line.lower() and self.HEADING_PATTERN.match(line):
                collecting = True
        # 标题不是 Markdown heading（例如写成粗体）时退回全文匹配，避免误报
        if not collecting:
            return text
        return "\n".join(part for part in body if part).strip()

    def _evidence_rows(self, text: str) -> list[str]:
        """抽取证据台账里的表格数据行（排除表头与分隔行）。"""
        labels = self.SECTION_RULES[2].labels + self._LEGACY_MOJIBAKE_LABELS.get("evidence", ())
        lowered = text.lower()
        matched = next((lb for lb in labels if lb.lower() in lowered), None)
        if matched is None:
            return []
        body = self._section_body(text, matched)

        rows = [
            line for line in body.splitlines()
            if self.MARKDOWN_ROW_PATTERN.match(line) and not self.SEPARATOR_ROW_PATTERN.match(line)
        ]
        # 首行是表头
        return rows[1:] if len(rows) > 1 else []

    def _has_bear_row(self, rows: list[str]) -> bool:
        return any(any(term in row.lower() for term in self.BEAR_TERMS) for row in rows)

    def _self_check_counts(self, text: str) -> dict:
        counts: dict[str, int | None] = {}
        for key, pattern in self.SELF_CHECK_PATTERNS.items():
            match = pattern.search(text)
            counts[key] = int(match.group(1)) if match else None
        return counts

    @staticmethod
    def _mentions_ticker(text: str, ticker: str) -> bool:
        symbol = (ticker or "").strip()
        if not symbol:
            return True
        if symbol.lower() in text.lower():
            return True
        # 000657.SZ 与正文里的 000657 应视为同一标的
        bare = re.split(r"[.\s]", symbol)[0]
        return bool(bare) and bare.lower() in text.lower()

    # --- prior-report conflicts ---------------------------------------------------

    def _find_prior_report_conflicts(self, current: str, prior_reports: Iterable[dict]) -> list[dict]:
        current_stance = self._stance(current)
        current_directions = self._directions(current)
        conflicts = []

        for report in prior_reports:
            prior_text = report.get("content", "") if isinstance(report, dict) else str(report)
            prior_stance = self._stance(prior_text)
            prior_directions = self._directions(prior_text)

            reasons = []
            if {current_stance, prior_stance} == {"bullish", "reject"}:
                reasons.append("action_reversal")
            for rule in self.DIRECTION_RULES:
                pair = {current_directions.get(rule.name), prior_directions.get(rule.name)}
                if pair == {"up", "down"}:
                    reasons.append(f"{rule.name}_direction_reversal")

            if reasons:
                conflicts.append({
                    "path": report.get("path", "") if isinstance(report, dict) else "",
                    "reasons": reasons,
                    "prior_stance": prior_stance,
                    "current_stance": current_stance,
                    "prior_directions": prior_directions,
                    "current_directions": current_directions,
                })

        return conflicts

    def _stance(self, text: str) -> str:
        if any(term in text for term in self.REJECT_TERMS):
            return "reject"
        if any(term in text for term in self.BULLISH_TERMS):
            return "bullish"
        return "neutral"

    def _directions(self, text: str) -> dict:
        """按规则表判断每个跟踪主题的方向，未提及则为 unknown。"""
        result = {}
        for rule in self.DIRECTION_RULES:
            if not any(term in text for term in rule.subject_terms):
                result[rule.name] = "unknown"
            elif any(term in text for term in rule.down_terms):
                result[rule.name] = "down"
            elif any(term in text for term in rule.up_terms):
                result[rule.name] = "up"
            else:
                result[rule.name] = "unknown"
        return result

    def _has_conflict_explanation(self, text: str) -> bool:
        return any(term in text for term in self.CONFLICT_EXPLANATION_TERMS)
