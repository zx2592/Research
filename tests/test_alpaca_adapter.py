"""
TDD Tests for services/execution/adapters/alpaca_adapter.py
"""
import sys
import pytest
from unittest.mock import MagicMock, patch

from core.artifacts.schemas import OrderIntent
from services.execution.adapters.alpaca_adapter import AlpacaAdapter


# Mock 'alpaca_trade_api' so we can test without pip installing it
mock_alpaca = MagicMock()
mock_rest_class = MagicMock()
mock_alpaca.REST = mock_rest_class
sys.modules["alpaca_trade_api"] = mock_alpaca

class TestAlpacaAdapter:
    def setup_method(self):
        # Reset mock call counts before each test
        mock_rest_class.reset_mock()

    def test_init_requires_credentials(self):
        with pytest.raises(ValueError, match="API key"):
            AlpacaAdapter(api_key="", secret_key="", base_url="")

    def test_init_with_credentials(self):
        adapter = AlpacaAdapter(api_key="K1", secret_key="S1", base_url="https://paper-api.alpaca.markets")
        assert adapter.api_key == "K1"

    def test_execute_market_buy_success(self):
        # Setup mock
        mock_rest_instance = mock_rest_class.return_value
        mock_order = MagicMock()
        mock_order.id = "alpaca-uuid-123"
        mock_order.status = "accepted"
        mock_order.filled_avg_price = None
        mock_rest_instance.submit_order.return_value = mock_order

        adapter = AlpacaAdapter(api_key="K", secret_key="S", base_url="B")
        intent = OrderIntent(
            ticker="NVDA", side="buy", quantity=10,
            order_type="market", rationale="test", confidence=0.9
        )
        
        # Execute
        result = adapter.execute(intent, prices={"NVDA": 130.0})
        
        # Assertions
        mock_rest_instance.submit_order.assert_called_once()
        _, kwargs = mock_rest_instance.submit_order.call_args
        assert kwargs["symbol"] == "NVDA"
        assert kwargs["qty"] == 10
        assert kwargs["side"] == "buy"
        assert kwargs["type"] == "market"
        assert kwargs["time_in_force"] == "day"
        
        assert result["ticker"] == "NVDA"
        assert result["broker_order_id"] == "alpaca-uuid-123"
        assert result["status"] == "accepted"

    def test_execute_limit_sell(self):
        mock_rest_instance = mock_rest_class.return_value
        mock_order = MagicMock()
        mock_order.id = "alpaca-uuid-456"
        mock_order.status = "accepted"
        mock_rest_instance.submit_order.return_value = mock_order

        adapter = AlpacaAdapter(api_key="K", secret_key="S", base_url="B")
        intent = OrderIntent(
            ticker="GOOG", side="sell", quantity=5,
            order_type="limit", limit_price=180.0, rationale="test", confidence=0.8
        )
        
        result = adapter.execute(intent, prices={})
        
        _, kwargs = mock_rest_instance.submit_order.call_args
        assert kwargs["type"] == "limit"
        assert kwargs["limit_price"] == 180.0

