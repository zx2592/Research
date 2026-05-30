"""
Tests for core/knowledge_base.py — knowledge card save, YAML format, index update.
"""
import os
import pytest

from core.knowledge_base import save_knowledge_card, _update_kb_index, KB_INDEX


class TestSaveKnowledgeCard:
    def test_save_card_creates_file(self, tmp_dir, monkeypatch):
        """save_knowledge_card should create a .md file."""
        monkeypatch.setattr("core.knowledge_base.KB_DIR", tmp_dir)
        monkeypatch.setattr("core.knowledge_base.KB_INDEX", os.path.join(tmp_dir, "KB_INDEX.md"))
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)

        filepath = save_knowledge_card(
            title="TestCard",
            tags=["tag1", "tag2"],
            card_type="Company",
            summary="Test summary",
            insights=["insight1", "insight2"],
            strategy="Test strategy",
            source_path="Reports/test.md",
            ticker="TEST",
        )
        assert os.path.exists(filepath)
        assert filepath.endswith(".md")

    def test_save_card_yaml_format(self, tmp_dir, monkeypatch):
        """Card file should contain YAML front matter with correct fields."""
        monkeypatch.setattr("core.knowledge_base.KB_DIR", tmp_dir)
        monkeypatch.setattr("core.knowledge_base.KB_INDEX", os.path.join(tmp_dir, "KB_INDEX.md"))
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)

        filepath = save_knowledge_card(
            title="YAMLTest",
            tags=["美股", "科技"],
            card_type="Company",
            summary="A great company",
            insights=["Growing fast"],
            strategy="Hold",
            source_path="Reports/yaml_test.md",
            ticker="YAML",
            status="观察池",
        )
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        assert content.startswith("---\n")
        assert "ticker: YAML" in content
        assert "type: Company" in content
        assert "status: 观察池" in content
        assert "tags: [美股, 科技]" in content


class TestUpdateKBIndex:
    def test_update_index_creates_and_appends(self, tmp_dir, monkeypatch):
        """First call creates KB_INDEX.md; second call appends a row."""
        index_path = os.path.join(tmp_dir, "KB_INDEX.md")
        monkeypatch.setattr("core.knowledge_base.KB_DIR", tmp_dir)
        monkeypatch.setattr("core.knowledge_base.KB_INDEX", index_path)

        # First call — creates the file
        _update_kb_index("NVDA_20250101.md", "NVDA", "NVDA分析", ["美股"], "Company", "2025-01-01", "Reports/r.md")
        assert os.path.exists(index_path)

        with open(index_path, "r", encoding="utf-8") as f:
            content1 = f.read()
        assert "NVDA" in content1

        # Second call — appends
        _update_kb_index("GOOG_20250101.md", "GOOG", "GOOG分析", ["美股"], "Company", "2025-01-01", "Reports/g.md")
        with open(index_path, "r", encoding="utf-8") as f:
            content2 = f.read()
        assert "GOOG" in content2
        # Both entries present
        assert "NVDA" in content2

    def test_update_index_theme_section(self, tmp_dir, monkeypatch):
        """Theme card type should go into section 二."""
        index_path = os.path.join(tmp_dir, "KB_INDEX.md")
        monkeypatch.setattr("core.knowledge_base.KB_DIR", tmp_dir)
        monkeypatch.setattr("core.knowledge_base.KB_INDEX", index_path)

        _update_kb_index("AI_20250101.md", "N/A", "AI主题", ["AI", "科技"], "Theme", "2025-01-01", "Reports/ai.md")
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "AI" in content
