"""
ArtifactSerializer — 工件序列化与反序列化

Saves artifacts to disk as Markdown + JSON metadata.
"""
import os
import json
from typing import Any, Dict, Union

from core.artifacts.schemas import (
    ResearchReport,
    DecisionAudit,
    OrderIntent,
    PortfolioSnapshot,
)


class ArtifactSerializer:
    """Serialize/deserialize artifacts to/from files."""

    @staticmethod
    def save(
        artifact: Union[ResearchReport, DecisionAudit, OrderIntent, PortfolioSnapshot],
        output_dir: str,
    ) -> Dict[str, str]:
        """
        Save an artifact to disk.

        Returns dict of file paths:
          - For ResearchReport/DecisionAudit: {"markdown": ..., "metadata": ...}
          - For OrderIntent/PortfolioSnapshot: {"json": ...}
        """
        os.makedirs(output_dir, exist_ok=True)

        if isinstance(artifact, ResearchReport):
            return ArtifactSerializer._save_research_report(artifact, output_dir)
        elif isinstance(artifact, DecisionAudit):
            return ArtifactSerializer._save_decision_audit(artifact, output_dir)
        elif isinstance(artifact, OrderIntent):
            return ArtifactSerializer._save_order_intent(artifact, output_dir)
        elif isinstance(artifact, PortfolioSnapshot):
            return ArtifactSerializer._save_portfolio_snapshot(artifact, output_dir)
        else:
            raise TypeError(f"Unknown artifact type: {type(artifact)}")

    @staticmethod
    def load_metadata(filepath: str) -> Dict[str, Any]:
        """Load metadata JSON from a file."""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── Private save methods ─────────────────────────────

    @staticmethod
    def _save_research_report(r: ResearchReport, output_dir: str) -> Dict[str, str]:
        base = f"{r.report_type}_{r.ticker}_{r.report_id}"
        md_path = os.path.join(output_dir, f"{base}.md")
        meta_path = os.path.join(output_dir, f"{base}_metadata.json")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(r.content_md)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(r.to_dict(), f, ensure_ascii=False, indent=2)

        return {"markdown": md_path, "metadata": meta_path}

    @staticmethod
    def _save_decision_audit(da: DecisionAudit, output_dir: str) -> Dict[str, str]:
        base = f"{da.action}_{da.ticker}_{da.audit_id}"
        md_path = os.path.join(output_dir, f"{base}_audit.md")
        meta_path = os.path.join(output_dir, f"{base}_metadata.json")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(da.content_md)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(da.to_dict(), f, ensure_ascii=False, indent=2)

        return {"markdown": md_path, "metadata": meta_path}

    @staticmethod
    def _save_order_intent(oi: OrderIntent, output_dir: str) -> Dict[str, str]:
        json_path = os.path.join(output_dir, f"order_{oi.ticker}_{oi.intent_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(oi.to_dict(), f, ensure_ascii=False, indent=2)
        return {"json": json_path}

    @staticmethod
    def _save_portfolio_snapshot(ps: PortfolioSnapshot, output_dir: str) -> Dict[str, str]:
        json_path = os.path.join(output_dir, f"snapshot_{ps.snapshot_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ps.to_dict(), f, ensure_ascii=False, indent=2)
        return {"json": json_path}
