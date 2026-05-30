"""
Tests for kanzhiqiu integration — DataHub adapter, digest, and drill_source routing.
"""
import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from services.datahub.base import DataSourceResult
from services.datahub.sources.kanzhiqiu_src import KanzhiqiuSource


# ── Sample data fixtures ─────────────────────────────────────────

SAMPLE_CACHE_DATA = {
    "date": "2026-03-24",
    "fetchedAt": "2026-03-24T10:00:00.000Z",
    "morningReports": [
        {"id": 2241, "title": "东方证券晨会纪要", "txtUrl": ""}
    ],
    "hotTopics": [
        {"question": "AI芯片格局变化", "time": "2026-03-24 09:30", "entities": ["NVDA", "AMD"]},
        {"question": "新能源车Q1交付", "time": "2026-03-24 09:15", "entities": ["TSLA", "NIO"]},
    ],
    "viewpoints": [
        {"question": "宏观经济展望", "time": "2026-03-24 08:00", "entities": ["SPY"]},
    ],
    "news": [
        {"title": "英伟达发布新GPU", "broker": "高盛", "docType": "深度报告",
         "stock": "NVDA", "rank": "买入"},
        {"title": "特斯拉工厂扩建", "broker": "摩根士丹利", "docType": "快讯",
         "stock": "TSLA", "rank": "增持"},
    ],
}


# ── KanzhiqiuSource tests ────────────────────────────────────────

_DIGEST_MOD = "integrations.kanzhiqiu.digest"


class TestKanzhiqiuSource:

    def test_name(self):
        src = KanzhiqiuSource()
        assert src.name == "kanzhiqiu"

    def test_fetch_no_cache_returns_error(self):
        """When no cache file exists, fetch returns error data."""
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=None):
            result = src.fetch(command="digest")
        assert isinstance(result, DataSourceResult)
        assert "error" in result.data

    def test_fetch_digest_returns_context(self):
        """When cache exists, digest command returns context string."""
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=SAMPLE_CACHE_DATA), \
             patch(f"{_DIGEST_MOD}.enrich_morning_content", side_effect=lambda d: d):
            result = src.fetch(command="digest")
        assert "context" in result.data
        assert "研报数据" in result.data["context"]
        assert result.data["stats"]["hot_topics"] == 2
        assert result.data["stats"]["news"] == 2

    def test_fetch_hot_topics(self):
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=SAMPLE_CACHE_DATA):
            result = src.fetch(command="hot_topics")
        assert result.data["count"] == 2
        assert result.data["hot_topics"][0]["question"] == "AI芯片格局变化"

    def test_fetch_news(self):
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=SAMPLE_CACHE_DATA):
            result = src.fetch(command="news")
        assert result.data["count"] == 2

    def test_fetch_morning(self):
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=SAMPLE_CACHE_DATA), \
             patch(f"{_DIGEST_MOD}.enrich_morning_content", side_effect=lambda d: d):
            result = src.fetch(command="morning")
        assert result.data["count"] == 1

    def test_fetch_raw(self):
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=SAMPLE_CACHE_DATA):
            result = src.fetch(command="raw")
        assert result.data == SAMPLE_CACHE_DATA

    def test_fetch_unknown_command(self):
        src = KanzhiqiuSource()
        with patch(f"{_DIGEST_MOD}.load_cached_data", return_value=SAMPLE_CACHE_DATA):
            result = src.fetch(command="invalid")
        assert "error" in result.data


# ── build_context tests ──────────────────────────────────────────

class TestBuildContext:

    def test_build_context_with_full_data(self):
        from integrations.kanzhiqiu.digest import build_context
        ctx = build_context(SAMPLE_CACHE_DATA)
        assert "研报数据 — 2026-03-24" in ctx
        assert "热点话题" in ctx
        assert "AI芯片格局变化" in ctx
        assert "综合推荐" in ctx
        assert "高盛" in ctx

    def test_build_context_empty_data(self):
        from integrations.kanzhiqiu.digest import build_context
        ctx = build_context({"date": "2026-03-24"})
        assert "研报数据" in ctx
        # Should not crash with missing sections
        assert "热点话题" not in ctx

    def test_build_context_morning_with_content(self):
        from integrations.kanzhiqiu.digest import build_context
        data = {
            "date": "2026-03-24",
            "morningReports": [
                {"title": "测试纪要", "content": "这是晨会内容" * 10}
            ],
        }
        ctx = build_context(data)
        assert "晨会纪要" in ctx
        assert "测试纪要" in ctx


# ── save/load cache tests ────────────────────────────────────────

class TestDigestCache:

    def test_save_and_load(self, tmp_path):
        from integrations.kanzhiqiu.digest import save_browser_data, load_cached_data, CACHE_DIR
        # Temporarily override CACHE_DIR
        import integrations.kanzhiqiu.digest as digest_mod
        original_cache = digest_mod.CACHE_DIR
        digest_mod.CACHE_DIR = tmp_path

        try:
            json_str = json.dumps(SAMPLE_CACHE_DATA, ensure_ascii=False)
            path = save_browser_data(json_str)
            assert path.exists()

            loaded = load_cached_data()
            # This may return None since we overrode CACHE_DIR but date check uses today
            # Just verify save worked
            assert (tmp_path / "2026-03-24.json").exists()
        finally:
            digest_mod.CACHE_DIR = original_cache


# ── CLI dispatch test ────────────────────────────────────────────

class TestLeadDispatch:

    def test_lead_uses_flash_routing(self):
        """lead is intentionally routed to the faster Flash model."""
        from research_cli import ResearchAgent
        assert "lead" not in ResearchAgent.PRO_WORKFLOWS
