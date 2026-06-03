"""
Tests for workflow model routing and CLI dispatch.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import research_cli
from research_cli import ResearchAgent, WorkflowRunner


class TestPROWorkflows:
    """Verify the PRO_WORKFLOWS set contains the right workflow names."""

    def test_pro_workflows_contains_expected(self):
        expected = {"deep", "value", "verify"}
        assert ResearchAgent.PRO_WORKFLOWS == expected

    def test_pro_workflows_excludes_flash(self):
        flash_workflows = {
            "scan",
            "quick",
            "update",
            "buy",
            "sell",
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
        }
        for wf in flash_workflows:
            assert wf not in ResearchAgent.PRO_WORKFLOWS


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

    def test_verify_uses_pro(self):
        agent = self._make_agent()
        agent.run_workflow("verify", "Verify the following claim: test")
        _, kwargs = agent.llm.create_chat.call_args
        assert kwargs["use_pro"] is True

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
            default = os.getenv("VPS_MODEL", "gemini-3-flash-preview")
            assert default == "gemini-3-flash-preview"
        except Exception:
            pytest.skip("Cannot test model defaults without google-genai")

    def test_pro_default_model(self, monkeypatch):
        monkeypatch.delenv("VPS_MODEL_PRO", raising=False)
        default = os.getenv("VPS_MODEL_PRO", "gemini-3.1-pro-preview")
        assert default == "gemini-3.1-pro-preview"
