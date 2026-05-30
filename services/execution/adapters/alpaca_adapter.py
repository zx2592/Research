"""
AlpacaAdapter — 真实/模拟盘交易执行器

Submits orders to Alpaca via alpaca-trade-api.
Can be used in the ExecutionPipeline instead of PaperAdapter.
Supports idempotent retry via client_order_id.
"""
import logging
import os
import time
from typing import Any, Dict, Optional

from core.artifacts.schemas import OrderIntent

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


class AlpacaAdapter:
    """Sends order intents to Alpaca REST API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        try:
            import alpaca_trade_api as tradeapi
            self._tradeapi = tradeapi
        except ImportError:
            raise ImportError(
                "alpaca-trade-api is required. Run: pip install alpaca-trade-api"
            )

        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.base_url = base_url or os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API key and Secret key must be provided")

        self.api = self._tradeapi.REST(
            key_id=self.api_key,
            secret_key=self.secret_key,
            base_url=self.base_url,
            api_version="v2",
        )

    def execute(self, intent: OrderIntent, prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Execute an OrderIntent via Alpaca with idempotent retry.

        Uses client_order_id to ensure at-most-once delivery.
        Retries on transient network errors with exponential backoff.
        """
        client_order_id = f"alpha_{intent.intent_id}"

        kwargs = {
            "symbol": intent.ticker,
            "qty": intent.quantity,
            "side": intent.side,
            "type": intent.order_type,
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }

        if intent.order_type == "limit":
            if not intent.limit_price:
                raise ValueError(f"limit_price required for limit orders: {intent.ticker}")
            kwargs["limit_price"] = intent.limit_price

        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                # Check if order already exists (idempotent recovery)
                if attempt > 0:
                    existing = self._find_existing_order(client_order_id)
                    if existing is not None:
                        logger.info("[Alpaca] 发现已存在订单 client_order_id=%s, 跳过重复提交", client_order_id)
                        return existing

                logger.info("[Alpaca] 提交订单 (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, kwargs)
                order = self.api.submit_order(**kwargs)
                logger.info("[Alpaca] 订单已提交: id=%s status=%s", order.id, order.status)

                return {
                    "ticker": intent.ticker,
                    "side": intent.side,
                    "quantity": intent.quantity,
                    "price": float(order.filled_avg_price) if getattr(order, "filled_avg_price", None) else None,
                    "status": order.status,
                    "broker_order_id": str(order.id),
                    "client_order_id": client_order_id,
                    "adapter": "alpaca",
                    "message": f"Alpaca {order.status}",
                }
            except Exception as e:
                last_exc = e
                # Don't retry on validation errors
                err_str = str(e).lower()
                if "invalid" in err_str or "insufficient" in err_str or "not found" in err_str:
                    logger.error("[Alpaca] 订单提交失败 (不可重试): %s", e)
                    raise
                logger.warning("[Alpaca] 订单提交失败 (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, e)
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    time.sleep(delay)

        logger.error("[Alpaca] 订单提交最终失败: %s", last_exc)
        raise last_exc

    def _find_existing_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Try to find an existing order by client_order_id."""
        try:
            order = self.api.get_order_by_client_order_id(client_order_id)
            return {
                "ticker": order.symbol,
                "side": order.side,
                "quantity": float(order.qty),
                "price": float(order.filled_avg_price) if getattr(order, "filled_avg_price", None) else None,
                "status": order.status,
                "broker_order_id": str(order.id),
                "client_order_id": client_order_id,
                "adapter": "alpaca",
                "message": f"Alpaca {order.status} (recovered)",
            }
        except Exception:
            return None
