"""
HealthChecker — 组合健康度检查

Checks portfolio snapshot for risk violations:
- Single position concentration (max weight %)
- Cash ratio
- Number of positions (diversification)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.portfolio.snapshot import PortfolioSnapshot


@dataclass
class HealthReport:
    """Results of a portfolio health check."""
    has_concentration_warning: bool = False
    concentrated_tickers: List[str] = field(default_factory=list)
    cash_pct: float = 0.0
    position_count: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "has_concentration_warning": self.has_concentration_warning,
            "concentrated_tickers": self.concentrated_tickers,
            "cash_pct": self.cash_pct,
            "position_count": self.position_count,
            "warnings": self.warnings,
        }


class HealthChecker:
    """Runs portfolio health checks against configured thresholds."""

    def __init__(
        self,
        max_single_position_pct: float = 15.0,
        min_cash_pct: float = 5.0,
        max_cash_pct: float = 60.0,
    ):
        self.max_single_position_pct = max_single_position_pct
        self.min_cash_pct = min_cash_pct
        self.max_cash_pct = max_cash_pct

    def check(self, snapshot: PortfolioSnapshot) -> HealthReport:
        """Run all health checks and return a HealthReport."""
        report = HealthReport()
        report.position_count = len(snapshot.positions)

        # Compute total NAV for weight calculation
        total_nav = snapshot.total_nav
        if total_nav is None or total_nav <= 0:
            # Fall back to cost-basis estimation
            cost_total = sum(p.cost_basis for p in snapshot.positions)
            total_nav = cost_total + snapshot.cash

        if total_nav <= 0:
            report.warnings.append("Cannot compute health: total NAV is zero")
            return report

        # Cash ratio
        report.cash_pct = (snapshot.cash / total_nav) * 100

        if report.cash_pct < self.min_cash_pct:
            report.warnings.append(
                f"Low cash: {report.cash_pct:.1f}% (min {self.min_cash_pct}%)"
            )
        if report.cash_pct > self.max_cash_pct:
            report.warnings.append(
                f"High cash: {report.cash_pct:.1f}% (max {self.max_cash_pct}%)"
            )

        # Concentration check
        for pos in snapshot.positions:
            # Use market value if available, else cost basis
            value = pos.market_value if pos.market_value is not None else pos.cost_basis
            weight = (value / total_nav) * 100
            if weight > self.max_single_position_pct:
                report.has_concentration_warning = True
                report.concentrated_tickers.append(pos.ticker)
                report.warnings.append(
                    f"Concentrated position: {pos.ticker} at {weight:.1f}% "
                    f"(max {self.max_single_position_pct}%)"
                )

        return report
