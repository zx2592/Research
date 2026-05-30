"""
ExecutionPipeline — 执行管线

Implements the stage → commit → guard → push → settle flow.
Inspired by OpenAlice's Wallet + Guard + Push semantics.

Flow:
  1. Check KillSwitch (hard stop, with lock held)
  2. Run GuardChain (risk checks)
  3. Commit to Wallet (audit record)
  4. Execute via Adapter (paper or live) — with compensation on failure
  5. Settle into Ledger (automatic in PaperAdapter)
"""
import logging
from typing import Any, Dict, Optional

from core.artifacts.schemas import OrderIntent
from services.execution.guards import GuardChain
from services.execution.kill_switch import KillSwitch
from services.execution.wallet import Wallet
from services.portfolio.ledger import PortfolioLedger

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when the pipeline rejects an order."""
    pass


class ExecutionPipeline:
    """
    Orchestrates the full order lifecycle:
    KillSwitch → GuardChain → Wallet.commit → Adapter.execute
    """

    def __init__(
        self,
        ledger: PortfolioLedger,
        wallet: Wallet,
        guard_chain: GuardChain,
        adapter,                    # PaperAdapter or LiveAdapter
        kill_switch: Optional[KillSwitch] = None,
    ):
        self.ledger = ledger
        self.wallet = wallet
        self.guard_chain = guard_chain
        self.adapter = adapter
        self.kill_switch = kill_switch

    def execute(
        self,
        intent: OrderIntent,
        prices: Optional[Dict[str, float]] = None,
        message: str = "",
    ) -> Dict[str, Any]:
        """
        Execute an OrderIntent through the full pipeline.

        Args:
            intent: The order to execute
            prices: Current market prices (ticker → price)
            message: Optional commit message

        Returns:
            Fill receipt dict

        Raises:
            PipelineError: if KillSwitch is active or any Guard fails
        """
        prices = prices or {}

        # 1. Kill switch check (with lock held to prevent TOCTTOU)
        if self.kill_switch:
            with self.kill_switch.check_and_hold() as (active, reason):
                if active:
                    logger.warning("KillSwitch 拦截订单: %s %s %s — %s",
                                   intent.side, intent.quantity, intent.ticker, reason)
                    raise PipelineError(
                        f"KillSwitch is active: {reason or 'no reason given'}"
                    )

        # 2. Guard chain (read-only, no side effects)
        result = self.guard_chain.run(intent, prices)
        if not result.passed:
            logger.info("Guard 拦截订单: %s %s %s — %s",
                        intent.side, intent.quantity, intent.ticker, result.reason)
            raise PipelineError(f"Guard blocked order: {result.reason}")

        # 3. Commit to wallet (audit trail)
        intent.status = "committed"
        commit_hash = self.wallet.commit(intent, message=message or f"Execute {intent.side} {intent.ticker}")

        # 4. Execute via adapter (compensate on failure)
        try:
            intent.status = "pushed"
            fill = self.adapter.execute(intent, prices)
        except Exception as exc:
            intent.status = "adapter_failed"
            self.wallet.commit(intent, message=f"COMPENSATE: {exc}")
            logger.error("Adapter 执行失败, 已写入补偿记录: %s %s %s — %s",
                         intent.side, intent.quantity, intent.ticker, exc)
            raise PipelineError(f"Adapter failed: {exc}") from exc

        # 5. Update status
        intent.status = "filled"
        fill["commit_hash"] = commit_hash
        logger.info("订单执行成功: %s %s %s, commit=%s",
                     intent.side, intent.quantity, intent.ticker, commit_hash)

        return fill
