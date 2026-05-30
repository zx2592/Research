"""
PortfolioSnapshot — 组合快照

Computed from replaying portfolio events.
Represents the state of the portfolio at a point in time.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class PositionState:
    """State of a single position."""
    ticker: str
    shares: float
    avg_cost: float     # weighted average cost per share
    cost_basis: float   # total cost basis (shares * avg_cost)
    # These are filled in when market prices are provided
    market_value: Optional[float] = None
    weight_pct: Optional[float] = None
    unrealized_pnl: Optional[float] = None


@dataclass
class PortfolioSnapshot:
    """Complete portfolio state at a point in time."""
    cash: float
    positions: List[PositionState] = field(default_factory=list)
    snapshot_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Computed fields (filled when prices are provided)
    total_equity: Optional[float] = None   # sum of market values
    total_nav: Optional[float] = None      # cash + total_equity

    def get_position(self, ticker: str) -> Optional[PositionState]:
        """Get a position by ticker, or None if not held."""
        for p in self.positions:
            if p.ticker == ticker:
                return p
        return None

    def enrich_with_prices(self, prices: Dict[str, float]) -> None:
        """Fill in market values and weight % using provided price quotes."""
        equity = 0.0
        for pos in self.positions:
            price = prices.get(pos.ticker)
            if price is not None:
                pos.market_value = pos.shares * price
                pos.unrealized_pnl = pos.market_value - pos.cost_basis
                equity += pos.market_value

        self.total_equity = equity
        self.total_nav = self.cash + equity

        # Compute weights
        if self.total_nav and self.total_nav > 0:
            for pos in self.positions:
                if pos.market_value is not None:
                    pos.weight_pct = (pos.market_value / self.total_nav) * 100

    def to_dict(self) -> dict:
        return {
            "snapshot_at": self.snapshot_at.isoformat(),
            "cash": self.cash,
            "total_nav": self.total_nav,
            "total_equity": self.total_equity,
            "positions": [
                {
                    "ticker": p.ticker,
                    "shares": p.shares,
                    "avg_cost": p.avg_cost,
                    "cost_basis": p.cost_basis,
                    "market_value": p.market_value,
                    "weight_pct": p.weight_pct,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in self.positions
            ],
        }
