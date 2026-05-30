"""
TDD Tests for core/artifacts/ — Standard Artifact Schemas

Tests written FIRST. Covers:
- ResearchReport schema
- DecisionAudit schema
- OrderIntent schema
- PortfolioSnapshot schema
- ArtifactSerializer: serialize/deserialize to MD + JSON
"""
import os
import json
from datetime import datetime, date, timezone

import pytest

from core.artifacts.schemas import (
    ResearchReport,
    DecisionAudit,
    OrderIntent,
    PortfolioSnapshot,
    PositionEntry,
)
from core.artifacts.serializer import ArtifactSerializer


# ── Schema creation & validation ──────────────────────────────────

class TestResearchReport:
    def test_create_minimal(self):
        r = ResearchReport(
            ticker="NVDA",
            report_type="deep",
            title="NVDA Deep Research",
            conclusion="Strong buy",
            confidence=0.85,
            content_md="# NVDA Analysis\n\nGreat company.",
        )
        assert r.ticker == "NVDA"
        assert r.confidence == 0.85
        assert r.report_id  # auto-generated

    def test_to_dict_roundtrip(self):
        r = ResearchReport(
            ticker="GOOG",
            report_type="value",
            title="GOOG Value",
            conclusion="Fair valued",
            confidence=0.7,
            content_md="# GOOG",
            tags=["tech", "search"],
        )
        d = r.to_dict()
        r2 = ResearchReport.from_dict(d)
        assert r2.ticker == r.ticker
        assert r2.tags == r.tags
        assert r2.report_id == r.report_id


class TestDecisionAudit:
    def test_create(self):
        da = DecisionAudit(
            ticker="NVDA",
            action="buy",
            rationale="Strong momentum + earnings beat",
            risk_factors=["Valuation stretched", "Macro uncertainty"],
            confidence=0.75,
            content_md="# Buy Audit: NVDA",
        )
        assert da.action == "buy"
        assert len(da.risk_factors) == 2

    def test_to_dict(self):
        da = DecisionAudit(
            ticker="SPOT",
            action="sell",
            rationale="Target reached",
            risk_factors=[],
            confidence=0.8,
            content_md="# Sell",
        )
        d = da.to_dict()
        assert d["action"] == "sell"
        assert d["ticker"] == "SPOT"


class TestOrderIntent:
    def test_create(self):
        oi = OrderIntent(
            ticker="NVDA",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=130.0,
            rationale="Post-earnings dip",
            confidence=0.8,
            source_audit_id="abc123",
        )
        assert oi.side == "buy"
        assert oi.quantity == 100
        assert oi.intent_id  # auto-generated

    def test_to_dict_json_serializable(self):
        oi = OrderIntent(
            ticker="GOOG",
            side="sell",
            quantity=50,
            order_type="market",
            rationale="Rebalance",
            confidence=0.6,
        )
        d = oi.to_dict()
        json.dumps(d)  # must not raise

    def test_status_lifecycle(self):
        oi = OrderIntent(
            ticker="V",
            side="buy",
            quantity=10,
            order_type="market",
            rationale="Add to core",
            confidence=0.9,
        )
        assert oi.status == "draft"
        oi.status = "staged"
        oi.status = "committed"
        assert oi.status == "committed"


class TestPortfolioSnapshot:
    def test_create_with_positions(self):
        ps = PortfolioSnapshot(
            total_nav=1000000.0,
            cash=200000.0,
            positions=[
                PositionEntry(ticker="NVDA", shares=100, market_value=13000.0,
                              cost_basis=12000.0, weight_pct=1.3),
                PositionEntry(ticker="GOOG", shares=50, market_value=9000.0,
                              cost_basis=10000.0, weight_pct=0.9),
            ],
        )
        assert len(ps.positions) == 2
        assert ps.total_nav == 1000000.0

    def test_to_dict(self):
        ps = PortfolioSnapshot(
            total_nav=500000.0,
            cash=50000.0,
            positions=[],
        )
        d = ps.to_dict()
        assert d["total_nav"] == 500000.0
        assert d["cash"] == 50000.0


# ── ArtifactSerializer ───────────────────────────────────────────

class TestArtifactSerializer:
    def test_save_research_report(self, tmp_dir):
        r = ResearchReport(
            ticker="NVDA",
            report_type="deep",
            title="NVDA Deep Research",
            conclusion="Strong buy",
            confidence=0.85,
            content_md="# NVDA Analysis\n\nDetails here.",
        )
        paths = ArtifactSerializer.save(r, output_dir=tmp_dir)
        assert os.path.exists(paths["markdown"])
        assert os.path.exists(paths["metadata"])

        # Markdown file should contain the content
        with open(paths["markdown"], "r", encoding="utf-8") as f:
            content = f.read()
        assert "NVDA Analysis" in content

        # Metadata should be valid JSON
        with open(paths["metadata"], "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["ticker"] == "NVDA"
        assert meta["confidence"] == 0.85

    def test_save_order_intent(self, tmp_dir):
        oi = OrderIntent(
            ticker="GOOG",
            side="buy",
            quantity=100,
            order_type="limit",
            limit_price=175.0,
            rationale="Value entry",
            confidence=0.7,
        )
        paths = ArtifactSerializer.save(oi, output_dir=tmp_dir)
        assert os.path.exists(paths["json"])

        with open(paths["json"], "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["ticker"] == "GOOG"
        assert data["side"] == "buy"

    def test_save_portfolio_snapshot(self, tmp_dir):
        ps = PortfolioSnapshot(
            total_nav=1000000.0,
            cash=200000.0,
            positions=[
                PositionEntry(ticker="NVDA", shares=100, market_value=13000.0,
                              cost_basis=12000.0, weight_pct=1.3),
            ],
        )
        paths = ArtifactSerializer.save(ps, output_dir=tmp_dir)
        assert os.path.exists(paths["json"])

    def test_load_metadata(self, tmp_dir):
        r = ResearchReport(
            ticker="SPOT",
            report_type="quick",
            title="SPOT Quick",
            conclusion="Hold",
            confidence=0.6,
            content_md="# Quick",
        )
        paths = ArtifactSerializer.save(r, output_dir=tmp_dir)
        loaded = ArtifactSerializer.load_metadata(paths["metadata"])
        assert loaded["ticker"] == "SPOT"
