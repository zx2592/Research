"""
Artifact Schemas — 标准工件数据结构

Defines the canonical data structures for all outputs:
- ResearchReport: /deep, /quick, /value, /scan results
- DecisionAudit: /buy, /sell audit reports
- OrderIntent: Machine-readable order intent for ExecutionGateway
- PortfolioSnapshot: Point-in-time portfolio state
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass
class ResearchReport:
    """Standard research output artifact."""
    ticker: str
    report_type: str            # "deep" / "quick" / "value" / "scan" / "update"
    title: str
    conclusion: str             # One-line conclusion
    confidence: float           # 0.0 - 1.0
    content_md: str             # Full Markdown content
    report_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "ticker": self.ticker,
            "report_type": self.report_type,
            "title": self.title,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResearchReport":
        ts = d.get("created_at")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            report_id=d["report_id"],
            ticker=d["ticker"],
            report_type=d["report_type"],
            title=d["title"],
            conclusion=d["conclusion"],
            confidence=d["confidence"],
            content_md=d.get("content_md", ""),
            created_at=ts or datetime.now(timezone.utc),
            tags=d.get("tags", []),
            sources=d.get("sources", []),
        )


@dataclass
class DecisionAudit:
    """Buy/Sell decision audit artifact."""
    ticker: str
    action: str                 # "buy" / "sell"
    rationale: str              # Core reasoning
    risk_factors: List[str]     # Identified risks
    confidence: float           # 0.0 - 1.0
    content_md: str             # Full Markdown audit report
    audit_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "ticker": self.ticker,
            "action": self.action,
            "rationale": self.rationale,
            "risk_factors": self.risk_factors,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class OrderIntent:
    """Machine-readable order intent for the ExecutionGateway."""
    ticker: str
    side: str                   # "buy" / "sell"
    quantity: float
    order_type: str             # "market" / "limit" / "stop"
    rationale: str
    confidence: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    source_audit_id: Optional[str] = None   # Links to DecisionAudit
    intent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "draft"       # "draft" / "staged" / "committed" / "pushed" / "filled" / "rejected"

    def __post_init__(self):
        # 规范化 + 验证 side
        self.side = self.side.lower().strip()
        if self.side not in {e.value for e in OrderSide}:
            raise ValueError(f"无效的 side: {self.side!r}，允许: buy, sell")
        # 规范化 + 验证 order_type
        self.order_type = self.order_type.lower().strip()
        if self.order_type not in {e.value for e in OrderType}:
            raise ValueError(f"无效的 order_type: {self.order_type!r}，允许: market, limit, stop")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "source_audit_id": self.source_audit_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PositionEntry:
    """A single position within a portfolio snapshot."""
    ticker: str
    shares: float
    market_value: float
    cost_basis: float
    weight_pct: float           # % of total NAV

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "shares": self.shares,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "weight_pct": self.weight_pct,
        }


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state."""
    total_nav: float
    cash: float
    positions: List[PositionEntry]
    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    snapshot_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "total_nav": self.total_nav,
            "cash": self.cash,
            "snapshot_at": self.snapshot_at.isoformat(),
            "positions": [p.to_dict() for p in self.positions],
        }
