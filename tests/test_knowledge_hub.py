"""
TDD Tests for core/knowledge/ — KnowledgeHub

Tests written FIRST. Covers:
- ReportMetadata: schema and CRUD
- KnowledgeIndex: index/search/list reports
- Full-text search over existing Reports/ directory
"""
import os
import json
import pytest

from core.knowledge.metadata import ReportMetadata, MetadataStore
from core.knowledge.index import KnowledgeIndex


# ── ReportMetadata ────────────────────────────────────────────────

class TestReportMetadata:
    def test_create_metadata(self):
        m = ReportMetadata(
            report_id="abc123",
            ticker="NVDA",
            report_type="deep",
            title="NVDA Deep Research",
            conclusion="Strong buy",
            confidence=0.85,
            tags=["semis", "AI"],
            source_file="deep_NVDA_abc123.md",
        )
        assert m.report_id == "abc123"
        assert "AI" in m.tags

    def test_to_dict_roundtrip(self):
        m = ReportMetadata(
            report_id="x1",
            ticker="GOOG",
            report_type="value",
            title="GOOG Value",
            conclusion="Fair value",
            confidence=0.7,
            tags=["tech"],
            source_file="value_GOOG.md",
        )
        d = m.to_dict()
        m2 = ReportMetadata.from_dict(d)
        assert m2.ticker == "GOOG"
        assert m2.confidence == 0.7
        assert m2.tags == ["tech"]

    def test_to_dict_json_serializable(self):
        m = ReportMetadata(
            report_id="y2",
            ticker="SPOT",
            report_type="quick",
            title="SPOT",
            conclusion="Hold",
            confidence=0.6,
            tags=[],
            source_file="quick_SPOT.md",
        )
        json.dumps(m.to_dict())


class TestMetadataStore:
    def test_save_and_load(self, tmp_dir):
        store = MetadataStore(store_path=os.path.join(tmp_dir, "meta.jsonl"))
        m = ReportMetadata(
            report_id="r1", ticker="NVDA", report_type="deep",
            title="NVDA", conclusion="Buy", confidence=0.9,
            tags=["AI"], source_file="d.md",
        )
        store.save(m)
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].ticker == "NVDA"

    def test_save_multiple(self, tmp_dir):
        store = MetadataStore(store_path=os.path.join(tmp_dir, "meta.jsonl"))
        for i, ticker in enumerate(["NVDA", "GOOG", "SPOT"]):
            store.save(ReportMetadata(
                report_id=f"r{i}", ticker=ticker, report_type="quick",
                title=ticker, conclusion="ok", confidence=0.7,
                tags=[], source_file=f"{ticker}.md",
            ))
        assert len(store.load_all()) == 3

    def test_find_by_ticker(self, tmp_dir):
        store = MetadataStore(store_path=os.path.join(tmp_dir, "meta.jsonl"))
        store.save(ReportMetadata("r1", "NVDA", "deep", "N1", "buy", 0.9, [], "n1.md"))
        store.save(ReportMetadata("r2", "GOOG", "deep", "G1", "hold", 0.7, [], "g1.md"))
        store.save(ReportMetadata("r3", "NVDA", "quick", "N2", "buy", 0.8, [], "n2.md"))
        nvda = store.find_by_ticker("NVDA")
        assert len(nvda) == 2

    def test_find_by_tag(self, tmp_dir):
        store = MetadataStore(store_path=os.path.join(tmp_dir, "meta.jsonl"))
        store.save(ReportMetadata("r1", "NVDA", "deep", "N", "buy", 0.9, ["AI", "semis"], "n.md"))
        store.save(ReportMetadata("r2", "GOOG", "deep", "G", "hold", 0.7, ["ads"], "g.md"))
        ai_reports = store.find_by_tag("AI")
        assert len(ai_reports) == 1
        assert ai_reports[0].ticker == "NVDA"


# ── KnowledgeIndex ────────────────────────────────────────────────

class TestKnowledgeIndex:
    def _make_reports(self, tmp_dir):
        """Create some fake .md reports in tmp_dir."""
        reports = {
            "nvda_deep.md": "# NVDA Deep Research\nStrong AI semiconductor play. Revenue grew 200%.",
            "goog_value.md": "# GOOG Value Analysis\nAdvertising moat remains intact. FCF yield attractive.",
            "spot_quick.md": "# SPOT Quick Note\nMonthly active users beat estimates. Gross margins expanding.",
        }
        for fname, content in reports.items():
            with open(os.path.join(tmp_dir, fname), "w", encoding="utf-8") as f:
                f.write(content)
        return tmp_dir

    def test_index_directory(self, tmp_dir):
        reports_dir = self._make_reports(tmp_dir)
        idx = KnowledgeIndex(reports_dir=reports_dir)
        idx.build()
        assert idx.count() == 3

    def test_search_by_keyword(self, tmp_dir):
        reports_dir = self._make_reports(tmp_dir)
        idx = KnowledgeIndex(reports_dir=reports_dir)
        idx.build()
        results = idx.search("semiconductor")
        assert len(results) >= 1
        assert any("nvda" in r["file"].lower() for r in results)

    def test_search_returns_snippet(self, tmp_dir):
        reports_dir = self._make_reports(tmp_dir)
        idx = KnowledgeIndex(reports_dir=reports_dir)
        idx.build()
        results = idx.search("advertising")
        assert len(results) >= 1
        assert results[0].get("snippet")

    def test_search_no_results(self, tmp_dir):
        reports_dir = self._make_reports(tmp_dir)
        idx = KnowledgeIndex(reports_dir=reports_dir)
        idx.build()
        results = idx.search("uranium mining blockchain")
        assert results == []

    def test_list_files(self, tmp_dir):
        reports_dir = self._make_reports(tmp_dir)
        idx = KnowledgeIndex(reports_dir=reports_dir)
        idx.build()
        files = idx.list_files()
        assert len(files) == 3
