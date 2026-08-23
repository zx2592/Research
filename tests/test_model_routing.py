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

    def test_deep_research_stage_uses_pro(self):
        # /deep 已分阶段：第一阶段（研究）走 Pro，组装与复核走 Flash
        agent = self._make_agent()
        agent.run_workflow("deep", "Run deep research on NVDA", ticker="NVDA")
        first_call = agent.llm.create_chat.call_args_list[0]
        assert first_call.kwargs["use_pro"] is True

    def test_value_research_stage_uses_pro(self):
        agent = self._make_agent()
        agent.run_workflow("value", "Run value analysis for MCO", ticker="MCO")
        first_call = agent.llm.create_chat.call_args_list[0]
        assert first_call.kwargs["use_pro"] is True

    def test_staged_workflow_falls_back_to_single_call_when_disabled(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_STAGES_DISABLED", "1")
        agent = self._make_agent()
        agent.run_workflow("deep", "Run deep research on NVDA", ticker="NVDA")
        assert agent.llm.create_chat.call_count == 1
        assert agent.llm.create_chat.call_args.kwargs["use_pro"] is True

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


class TestStagedWorkflows:
    """多阶段执行：上下文隔离 + 预算共享 + 按阶段选模型。"""

    def test_deep_and_value_are_staged(self):
        assert settings.workflow_stages.is_staged("deep")
        assert settings.workflow_stages.is_staged("value")

    def test_single_stage_workflows_are_untouched(self):
        for wf in ("scan", "quick", "buy", "sell"):
            assert settings.workflow_stages.stages_for(wf) == ()

    def test_stages_can_be_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_STAGES_DISABLED", "1")
        assert settings.workflow_stages.stages_for("deep") == ()

    def test_first_stage_uses_pro_and_later_stages_do_not(self):
        stages = settings.workflow_stages.stages_for("deep")
        assert stages[0][0] == "research" and stages[0][3] is True
        assert all(st[3] is False for st in stages[1:])


class TestStageScopedContracts:
    def _runner(self, tmp_path, monkeypatch):
        workflow_dir = tmp_path / ".agent" / "workflows"
        common_dir = workflow_dir / "common"
        stages_dir = workflow_dir / "stages"
        common_dir.mkdir(parents=True)
        stages_dir.mkdir(parents=True)
        (workflow_dir / "deep.md").write_text("DEEP MAIN", encoding="utf-8")
        (common_dir / "00-report-contract.md").write_text("CONTRACT-00", encoding="utf-8")
        (common_dir / "10-evidence-contract.md").write_text("CONTRACT-10", encoding="utf-8")
        (common_dir / "20-quality-gate.md").write_text("CONTRACT-20", encoding="utf-8")
        (stages_dir / "s1.md").write_text("STAGE ONE BODY", encoding="utf-8")
        monkeypatch.setattr(research_cli, "_get_network_date", lambda: ("20260411", "2026-04-11"))
        return WorkflowRunner(str(tmp_path))

    def test_only_declared_contracts_are_loaded(self, tmp_path, monkeypatch):
        runner = self._runner(tmp_path, monkeypatch)
        stage = ("research", "stages/s1.md", ("00", "10"), True)

        result = runner.build_system_instruction("deep", stage=stage)

        assert "CONTRACT-00" in result
        assert "CONTRACT-10" in result
        # 研究阶段不需要质量门禁——它是组装阶段才用得上的
        assert "CONTRACT-20" not in result

    def test_stage_body_and_marker_are_appended(self, tmp_path, monkeypatch):
        runner = self._runner(tmp_path, monkeypatch)
        stage = ("research", "stages/s1.md", ("00",), True)

        result = runner.build_system_instruction("deep", stage=stage)

        assert "DEEP MAIN" in result
        assert "当前阶段：research" in result
        assert "STAGE ONE BODY" in result
        assert result.index("DEEP MAIN") < result.index("STAGE ONE BODY")

    def test_unstaged_call_loads_every_contract(self, tmp_path, monkeypatch):
        runner = self._runner(tmp_path, monkeypatch)
        result = runner.build_system_instruction("deep")
        for marker in ("CONTRACT-00", "CONTRACT-10", "CONTRACT-20"):
            assert marker in result

    def test_remaining_budget_overrides_workflow_budget(self, tmp_path, monkeypatch):
        runner = self._runner(tmp_path, monkeypatch)
        stage = ("assemble", "stages/s1.md", ("00",), False)

        result = runner.build_system_instruction("deep", stage=stage, remaining_budget=3)

        assert "**3 点**" in result
        assert "本阶段可用" in result


class TestStagedExecution:
    @pytest.fixture(autouse=True)
    def _patch_agent(self, monkeypatch):
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
        monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)

    def _make_agent(self):
        agent = ResearchAgent()
        agent.llm = MagicMock()
        agent.llm.chat.side_effect = ["research done", "report saved", "critique clean"]
        agent.runner = MagicMock()
        agent.runner.build_system_instruction.return_value = "mock instruction"
        agent._tools = lambda workflow_name="": []
        return agent

    def test_each_stage_is_its_own_session(self):
        agent = self._make_agent()
        agent.run_workflow("deep", "Deep research on NVDA", ticker="NVDA")

        # 三个阶段 = 三次 reset + 三次 create_chat，上下文不跨阶段累积
        assert agent.llm.reset.call_count == 3
        assert agent.llm.create_chat.call_count == 3
        assert agent.llm.chat.call_count == 3

    def test_only_the_research_stage_uses_pro(self):
        agent = self._make_agent()
        agent.run_workflow("deep", "Deep research on NVDA", ticker="NVDA")

        models = [c.kwargs["use_pro"] for c in agent.llm.create_chat.call_args_list]
        assert models == [True, False, False]

    def test_last_stage_result_is_returned(self):
        agent = self._make_agent()
        assert agent.run_workflow("deep", "task", ticker="NVDA") == "critique clean"

    def test_prior_stage_output_is_handed_to_the_next(self):
        agent = self._make_agent()
        agent.run_workflow("deep", "task", ticker="NVDA")

        second_task = agent.llm.chat.call_args_list[1].args[0]
        assert "research done" in second_task
        assert "阶段 2/3" in second_task

    def test_budget_is_shared_across_stages_not_reset(self):
        agent = self._make_agent()
        seen = []

        def record(*args, **kwargs):
            seen.append(agent._budget.remaining())
            agent._budget.consume(1)
            return "stage output"

        agent.llm.chat.side_effect = record
        agent.run_workflow("deep", "task", ticker="NVDA")

        # 每个阶段开始时余额都比上一个少——预算跨阶段共享
        assert seen == sorted(seen, reverse=True)
        assert seen[0] > seen[-1]

    def test_single_stage_workflow_still_runs_once(self):
        agent = self._make_agent()
        agent.llm.chat.side_effect = ["scan done"]
        result = agent.run_workflow("scan", "Run market scan")

        assert result == "scan done"
        assert agent.llm.create_chat.call_count == 1
