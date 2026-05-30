"""
Tests for core/data_manager.py — DataManager search counter, holdings loading.
"""
import os
import json
import pytest

import core.data_manager as data_manager_module
from core.data_manager import DataManager, load_holdings


class TestSearchCounter:
    def test_counter_is_per_instance(self):
        """Two DataManager instances should have independent counters."""
        dm1 = DataManager()
        dm2 = DataManager()
        # Simulate searches on dm1 (will fail without API key, but counter still increments)
        dm1._search_count = 5
        assert dm2._search_count == 0

    def test_reset_clears_counter(self):
        dm = DataManager()
        dm._search_count = 4
        dm.reset_search_counter()
        assert dm._search_count == 0

    def test_search_quota_exceeded(self, monkeypatch):
        """After max_searches, search_web returns quota message."""
        dm = DataManager()
        dm.max_searches = 2
        dm._search_count = 2  # already at limit
        result = dm.search_web("test query")
        assert "搜索配额已用完" in result

    def test_search_web_missing_key(self, monkeypatch):
        """Without TAVILY_API_KEY, search_web returns error string."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        dm = DataManager()
        dm.tavily_key = None
        result = dm.search_web("test query")
        assert "TAVILY_API_KEY" in result

    def test_default_max_searches(self):
        dm = DataManager()
        assert dm.max_searches == 8


class TestLoadHoldings:
    def test_load_holdings_missing_file(self, tmp_dir):
        """If holdings.json doesn't exist, return empty dict."""
        result = load_holdings(tmp_dir)
        assert result == {}


class TestFetchMarketPrices:
    def test_direct_quote_path_computes_daily_change(self, tmp_dir, monkeypatch):
        config_dir = os.path.join(tmp_dir, "Config")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "holdings.json"), "w", encoding="utf-8") as handle:
            json.dump({"tickers": {"NVDA": {}}}, handle)

        monkeypatch.setattr(data_manager_module, "PROJECT_ROOT", tmp_dir)
        monkeypatch.setattr(
            data_manager_module,
            "load_holdings",
            lambda _root: {"NVDA": {"name": "NVIDIA", "type": "stock", "logic": "-", "risk": "-"}},
        )
        monkeypatch.setattr(
            "services.datahub.sources.yfinance_src._fetch_quote_via_urllib",
            lambda ticker: {"price": 105.0, "previous_close": 100.0},
        )

        dm = DataManager()

        result = dm.fetch_market_prices()

        assert len(result) == 1
        assert result[0]["price"] == 105.0
        assert result[0]["change"] == pytest.approx(5.0)

    def test_load_holdings_valid_file(self, tmp_dir):
        """Correctly parse a valid holdings.json."""
        config_dir = os.path.join(tmp_dir, "Config")
        os.makedirs(config_dir)
        holdings = {
            "tickers": {
                "NVDA": {"sector": "Tech", "strategy": "Core"},
                "GOOG": {"sector": "Tech", "strategy": "Short-Term Satellite"},
            }
        }
        with open(os.path.join(config_dir, "holdings.json"), "w") as f:
            json.dump(holdings, f)

        result = load_holdings(tmp_dir)
        assert "NVDA" in result
        assert "GOOG" in result
        assert result["NVDA"]["risk"] == "Low"  # Core strategy → Low
        assert result["GOOG"]["risk"] == "High"  # Short-Term Satellite → High

    def test_load_holdings_corrupt_json(self, tmp_dir):
        """Corrupt JSON should return empty dict, not crash."""
        config_dir = os.path.join(tmp_dir, "Config")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "holdings.json"), "w") as f:
            f.write("{invalid json")

        result = load_holdings(tmp_dir)
        assert result == {}
