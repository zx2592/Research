"""
HoldingsImporter — Holdings JSON → Portfolio Events

Genesis importer: converts Config/holdings.json
(the current manual snapshot) into a list of FillEvents
and a CashFlowEvent so the PortfolioLedger can be seeded.

This runs ONCE when migrating from V2.5 → V3.
After that, all changes flow through real FillEvents from the broker.
"""
import json
from datetime import datetime, timezone
from typing import List

from services.portfolio.events import CashFlowEvent, FillEvent, PortfolioEvent


class HoldingsImporter:
    """Converts holdings.json into portfolio events for genesis import."""

    def import_from_holdings_json(self, filepath: str) -> List[PortfolioEvent]:
        """
        Read holdings.json and produce a list of events that would
        reproduce the current positions if replayed from scratch.

        Strategy:
          1. Compute total capital = sum(cost_basis_usd) + extra_cash_usd
          2. Add a CashFlowEvent(deposit) for total capital
          3. For each ticker, add a FillEvent(buy) at avg_cost_usd
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        events: List[PortfolioEvent] = []
        # Use a fixed genesis timestamp so replays are deterministic
        genesis_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)

        tickers = data.get("tickers", {})
        extra_cash = float(data.get("extra_cash_usd", 0.0))

        # Compute total capital needed = cost basis of all positions + extra cash
        total_cost_basis = sum(
            float(info.get("cost_basis_usd", 0.0))
            for info in tickers.values()
        )
        total_capital = total_cost_basis + extra_cash

        # 1. Single genesis deposit covering all capital
        if total_capital > 0:
            e = CashFlowEvent(amount=total_capital, currency="USD", category="deposit")
            e.timestamp = genesis_ts
            events.append(e)

        # 2. Position fills (synthetic buy at avg cost)
        for ticker, info in tickers.items():
            shares = float(info.get("total_shares", 0))
            avg_cost = float(info.get("avg_cost_usd", 0))
            cost_basis = float(info.get("cost_basis_usd", shares * avg_cost))

            if shares <= 0:
                continue

            price = avg_cost if avg_cost > 0 else (cost_basis / shares if shares > 0 else 0)
            accounts = info.get("accounts", ["genesis"])
            account = accounts[0] if accounts else "genesis"

            fill = FillEvent(
                ticker=ticker,
                side="buy",
                quantity=shares,
                price=price,
                commission=0.0,
                account=account,
            )
            fill.timestamp = genesis_ts
            events.append(fill)

        return events
