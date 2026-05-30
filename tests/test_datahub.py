"""
TDD Tests for services/datahub/ — DataHub

Tests written FIRST. Covers:
- DataSource abstract interface
- DataHub: register source, fetch with cache, version tracking
- Cache: file-based caching with TTL
- Mock source adapters
"""
import os
import json
import time
import pytest

from services.datahub.base import DataSource, DataSourceResult
from services.datahub.cache import DataCache
from services.datahub.hub import DataHub


# ── DataSource (mock) ─────────────────────────────────────────────

class MockPriceSource(DataSource):
    """Test double for a price data source."""
    name = "mock_price"
    call_count = 0

    def fetch(self, ticker: str, **kwargs) -> DataSourceResult:
        MockPriceSource.call_count += 1
        return DataSourceResult(
            source_name=self.name,
            data={"ticker": ticker, "price": 130.0, "call": MockPriceSource.call_count},
            query=ticker,
        )


class MockSearchSource(DataSource):
    """Test double for a search source (budget-consuming)."""
    name = "mock_search"

    def fetch(self, query: str, **kwargs) -> DataSourceResult:
        return DataSourceResult(
            source_name=self.name,
            data={"results": [f"result for {query}"]},
            query=query,
        )


class TestDataSourceResult:
    def test_create(self):
        r = DataSourceResult(source_name="test", data={"x": 1}, query="NVDA")
        assert r.source_name == "test"
        assert r.data["x"] == 1
        assert r.version  # auto-generated

    def test_to_dict(self):
        r = DataSourceResult(source_name="yfinance", data={"price": 130.0}, query="NVDA")
        d = r.to_dict()
        assert d["source_name"] == "yfinance"
        assert d["data"]["price"] == 130.0
        json.dumps(d)  # must be serializable


# ── DataCache ────────────────────────────────────────────────────

class TestDataCache:
    def test_miss_returns_none(self, tmp_dir):
        cache = DataCache(cache_dir=tmp_dir, default_ttl=60)
        result = cache.get("price", "NVDA")
        assert result is None

    def test_set_and_get(self, tmp_dir):
        cache = DataCache(cache_dir=tmp_dir, default_ttl=60)
        data = {"price": 130.0}
        cache.set("price", "NVDA", data)
        result = cache.get("price", "NVDA")
        assert result == data

    def test_expired_returns_none(self, tmp_dir):
        cache = DataCache(cache_dir=tmp_dir, default_ttl=0)  # expires immediately
        cache.set("price", "NVDA", {"price": 130.0})
        time.sleep(0.05)
        result = cache.get("price", "NVDA")
        assert result is None

    def test_different_keys_isolated(self, tmp_dir):
        cache = DataCache(cache_dir=tmp_dir, default_ttl=60)
        cache.set("price", "NVDA", {"p": 130.0})
        cache.set("price", "GOOG", {"p": 175.0})
        assert cache.get("price", "NVDA")["p"] == 130.0
        assert cache.get("price", "GOOG")["p"] == 175.0

    def test_invalidate(self, tmp_dir):
        cache = DataCache(cache_dir=tmp_dir, default_ttl=60)
        cache.set("price", "NVDA", {"p": 130.0})
        cache.invalidate("price", "NVDA")
        assert cache.get("price", "NVDA") is None


# ── DataHub ──────────────────────────────────────────────────────

class TestDataHub:
    def _make_hub(self, tmp_dir):
        MockPriceSource.call_count = 0
        cache = DataCache(cache_dir=tmp_dir, default_ttl=60)
        hub = DataHub(cache=cache)
        hub.register(MockPriceSource())
        hub.register(MockSearchSource())
        return hub

    def test_register_and_fetch(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        result = hub.fetch("mock_price", ticker="NVDA")
        assert result.data["ticker"] == "NVDA"
        assert result.source_name == "mock_price"

    def test_fetch_unknown_source_raises(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        with pytest.raises(KeyError, match="not registered"):
            hub.fetch("unknown_source", ticker="NVDA")

    def test_fetch_with_cache_hit(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        result1 = hub.fetch("mock_price", ticker="NVDA")
        call_after_first = MockPriceSource.call_count
        result2 = hub.fetch("mock_price", ticker="NVDA")
        # Second call should hit cache — call_count should not increase
        assert MockPriceSource.call_count == call_after_first
        assert result2.data["price"] == 130.0

    def test_fetch_bypass_cache(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        hub.fetch("mock_price", ticker="NVDA")
        before_count = MockPriceSource.call_count
        hub.fetch("mock_price", ticker="NVDA", bypass_cache=True)
        assert MockPriceSource.call_count == before_count + 1

    def test_list_sources(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        sources = hub.list_sources()
        assert set(sources) == {"mock_price", "mock_search"}

    def test_result_has_version(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        result = hub.fetch("mock_search", query="NVDA earnings")
        assert result.version  # non-empty version string

    def test_fetch_search_source(self, tmp_dir):
        hub = self._make_hub(tmp_dir)
        result = hub.fetch("mock_search", query="NVDA earnings 2026")
        assert len(result.data["results"]) > 0


# ── OpenBBSource ──────────────────────────────────────────────────

class TestOpenBBSource:
    """
    OpenBB tests run in 'no-install' mode:
    openbb is likely not installed in test env, so we test graceful degradation.
    The adapter returns error dict (not raises) when library is missing.
    """

    def test_returns_data_source_result(self):
        from services.datahub.sources.openbb_src import OpenBBSource
        src = OpenBBSource()
        result = src.fetch(ticker="NVDA", data_type="price")
        assert isinstance(result.data, dict)
        assert result.source_name == "openbb"

    def test_graceful_when_not_installed(self):
        """If openbb not installed, returns error dict instead of crashing."""
        from services.datahub.sources.openbb_src import OpenBBSource
        src = OpenBBSource()
        result = src.fetch(ticker="NVDA", data_type="price")
        # Either installed (has 'latest') or not (has 'error')
        assert "error" in result.data or "latest" in result.data

    def test_unknown_data_type_returns_error(self):
        from services.datahub.sources.openbb_src import OpenBBSource
        src = OpenBBSource()
        result = src.fetch(ticker="NVDA", data_type="unknown_type")
        # Should return error dict, not raise
        assert "error" in result.data

    def test_registers_in_hub(self, tmp_dir):
        from services.datahub.sources.openbb_src import OpenBBSource
        hub = DataHub(cache=DataCache(cache_dir=tmp_dir, default_ttl=60))
        hub.register(OpenBBSource())
        assert "openbb" in hub.list_sources()

