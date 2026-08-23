"""
Tests for workflow model routing and CLI dispatch.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import research_cli
from core import settings
from research_cli import ResearchAgent, WorkflowRunner


class TestPROWorkflows:
    """Verify the PRO_WORKFLOWS set contains the right workflow names."""

    def test_pro_workflows_contains_expected(self):
        # buy/sell 触碰真实下单，与建档级深研同属高后果任务，一并走 Pro
        expected = {"deep", "value", "buy", "sell"}
        assert ResearchAgent.PRO_WORKFLOWS == expected

    def test_pro_workflows_excludes_flash(self):
        flash_workflows = {
            "scan",
            "quick",
            "update",
            "position",
            "lead",
            "rethink",
            "add",
            "option",
            "macro",
            "optimize",
            "theme",
            "core",
            "insight",
            "verify",
        }
        for wf in flash_workflows:
            assert wf not in ResearchAgent.PRO_WORKFLOWS

    def test_pro_workflows_can_be_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv("PRO_WORKFLOWS", "deep, macro")
        assert settings.model_routing.pro_workflows() == {"deep", "macro"}


class TestWorkflowSearchBudget:
    """预算是单一真理源：settings 声明、工具层强制、提示词注入同一个数字。"""

    def test_per_workflow_budget_differs_by_weight(self):
        assert settings.workflow_budget.for_workflow("scan") == 28
        assert settings.workflow_budget.for_workflow("quick") == 2
        assert settings.workflow_budget.for_workflow("add") == 0

    def test_unknown_workflow_falls_back_to_default(self):
        assert settings.workflow_budget.for_workflow("nope") == settings.workflow_budget.DEFAULT

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("SEARCH_BUDGET_SCAN", "3")
        assert settings.workflow_budget.for_workflow("scan") == 3

    def test_build_system_instruction_injects_budget(self, tmp_path, monkeypatch):
        workflow_dir = tmp_path / ".agent" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "quick.md").write_text("QUICK BODY", encoding="utf-8")
        monkeypatch.setattr(research_cli, "_get_network_date", lambda: ("20260411", "2026-04-11"))

        result = WorkflowRunner(str(tmp_path)).build_system_instruction("quick")

        assert "Search Budget" in result
        assert "**2 点**" in result


class TestRunWorkflowModelRouting:
    """Verify run_workflow passes use_pro correctly based on workflow name."""

    @pytest.fixture(autouse=True)
    def _patch_agent(self, monkeypatch):
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
        monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)

    def _make_agent(self):
        agent = ResearchAgent()
        agent.llm = MagicMock()
        agent.runner = MagicMock()
        agent.runner.build_system_instruction.return_value = "mock system instruction"
        return agent

    def test_deep_uses_pro(self):
        agent = self._make_agent()
        agent.run_workflow("deep", "Run deep research on NVDA", ticker="NVDA")
        _, kwargs = agent.llm.create_chat.call_args
        assert kwargs["use_pro"] is True

    def test_value_uses_pro(self):
        agent = self._make_agent()
        agent.run_workflow("value", "Run value analysis for MCO", ticker="MCO")
        _, kwargs = agent.llm.create_chat.call_args
        assert kwargs["use_pro"] is True

    def test_verify_uses_flash(self):
        agent = self._make_agent()
        agent.run_workflow("verify", "Verify the following claim: test")
        _, kwargs = agent.llm.create_chat.call_args
        assert kwargs["use_pro"] is False

    def test_scan_uses_flash(self):
        agent = self._make_agent()
        agent.run_workflow("scan", "Run full market scan")
        _, kwargs = agent.llm.create_chat.call_args
        assert kwargs["use_pro"] is False

    def test_quick_uses_flash(self):
        agent = self._make_agent()
        agent.run_workflow("quick", "Quick event review for TSLA", ticker="TSLA")
        _, kwargs = agent.llm.create_chat.call_args
        assert kwargs["use_pro"] is False


class TestWorkflowRunnerRssDate:
    def test_load_latest_rss_uses_network_date_anchor(self, tmp_path, monkeypatch):
        raw_dir = tmp_path / "Reports" / "Raw_Data" / "2026-04"
        raw_dir.mkdir(parents=True)
        rss_file = raw_dir / "financial_data_20260410.json"
        rss_file.write_text('{"headline":"anchored"}', encoding="utf-8")

        monkeypatch.setattr(research_cli, "_get_network_date", lambda: ("20260411", "2026-04-11"))

        runner = WorkflowRunner(str(tmp_path))

        result = runner.load_latest_rss()

        assert "20260410" in result
        assert "anchored" in result

    def test_build_system_instruction_injects_common_quality_rules(self, tmp_path, monkeypatch):
        workflow_dir = tmp_path / ".agent" / "workflows"
        common_dir = workflow_dir / "common"
        common_dir.mkdir(parents=True)
        (workflow_dir / "scan.md").write_text("SCAN WORKFLOW BODY", encoding="utf-8")
        (common_dir / "00-report-contract.md").write_text("COMMON REPORT CONTRACT", encoding="utf-8")
        (common_dir / "10-quality-gate.md").write_text("COMMON QUALITY GATE", encoding="utf-8")

        monkeypatch.setattr(research_cli, "_get_network_date", lambda: ("20260411", "2026-04-11"))

        runner = WorkflowRunner(str(tmp_path))

        result = runner.build_system_instruction("scan")

        assert "COMMON REPORT CONTRACT" in result
        assert "COMMON QUALITY GATE" in result
        assert "SCAN WORKFLOW BODY" in result
        assert result.index("COMMON REPORT CONTRACT") < result.index("SCAN WORKFLOW BODY")


class TestCliDispatch:
    def test_optimize_dispatches_workflow(self, monkeypatch):
        agent = MagicMock()
        monkeypatch.setattr(research_cli, "ResearchAgent", MagicMock(return_value=agent))
        monkeypatch.setattr(sys, "argv", ["research_cli.py", "optimize", "minvol"])

        research_cli.main()

        agent.run_workflow.assert_called_once_with(
            "optimize",
            "Run the portfolio optimization workflow with this input: minvol.",
            ticker=None,
        )

    def test_main_prints_workflow_result(self, monkeypatch, capsys):
        agent = MagicMock()
        agent.run_workflow.return_value = "Report saved"
        monkeypatch.setattr(research_cli, "ResearchAgent", MagicMock(return_value=agent))
        monkeypatch.setattr(sys, "argv", ["research_cli.py", "scan"])

        research_cli.main()

        assert "Report saved" in capsys.readouterr().out

    def test_main_exits_nonzero_on_error_result(self, monkeypatch, capsys):
        agent = MagicMock()
        agent.run_workflow.return_value = "Error: adapter failed"
        monkeypatch.setattr(research_cli, "ResearchAgent", MagicMock(return_value=agent))
        monkeypatch.setattr(sys, "argv", ["research_cli.py", "scan"])

        with pytest.raises(SystemExit) as exc:
            research_cli.main()

        assert exc.value.code == 1
        assert "Error: adapter failed" in capsys.readouterr().out


class TestDefaultModelNames:
    """Verify the default model name constants in LLMClient."""

    def test_flash_default_model(self, monkeypatch):
        monkeypatch.delenv("VPS_MODEL", raising=False)
        monkeypatch.delenv("VPS_MODEL_PRO", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        try:
            from core.llm_client import LLMClient

            LLMClient()
            default = os.getenv("VPS_MODEL", "gemini-3-flash")
            assert default == "gemini-3-flash"
        except Exception:
            pytest.skip("Cannot test model defaults without google-genai")

    def test_pro_default_model(self, monkeypatch):
        monkeypatch.delenv("VPS_MODEL_PRO", raising=False)
        default = os.getenv("VPS_MODEL_PRO", "gemini-3.1-pro")
        assert default == "gemini-3.1-pro"
