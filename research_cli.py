#!/usr/bin/env python3
"""
Research System CLI Runner
v3.88 (v1.6.1 integration + CORE holdings + No Kanzhiqiu)

VPS 环境下通过 Gemini API 执行研究命令。桌面环境请直接使用 IDE Agent。
Usage:
    python research_cli.py scan
    python research_cli.py deep NVDA
    python research_cli.py quick TSLA "Robotaxi event"
    python research_cli.py value MCO
    python research_cli.py verify "iPhone 18 titanium rumor"
    python research_cli.py add
    python research_cli.py insight          # Market Insight
    python research_cli.py theme            # Momentum Theme Checklist
"""

import logging
import os
import sys
import argparse
import json
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Project root - always the directory containing this file (research/)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.llm_client import LLMClient, LLMConfigError
from core.data_manager import DataManager
from core.artifacts.schemas import OrderIntent
from core import settings
from core.tool_factory import ToolFactory
from core.toolbus.budget import BudgetManager
from core.network_time import get_network_date
from services.portfolio.ledger import PortfolioLedger
from services.execution.pipeline import ExecutionPipeline
from services.execution.wallet import Wallet
from services.execution.guards import GuardChain, MaxPositionGuard, CooldownGuard, ReverseCooldownGuard
from services.execution.kill_switch import KillSwitch
from services.execution.adapters.paper import PaperAdapter
from services.datahub.hub import DataHub
from services.datahub.sources import (
    BBBrowserSource,
    EastmoneySource,
    OpenCLISource,
    TencentQuoteSource,
    YFinanceSource,
)


# --- Network Time Utility ---

def _get_network_date() -> tuple[str, str]:
    """获取网络日期字符串 (YYYYMMDD, YYYY-MM-DD)，失败时回退到系统时钟。"""
    return get_network_date(logger=logger)


# --- Python-side Context Pre-loader ---

class WorkflowRunner:
    """
    Python 侧上下文预加载器。
    所有确定性文件 I/O 在此完成，不消耗 LLM token。
    """

    # 需要 RSS 数据的 workflow
    RSS_WORKFLOWS = {"scan", "quick", "update", "macro"}

    def __init__(self, root: str):
        self.root = root
        self._date_compact, self._date_iso = _get_network_date()

    def _read(self, rel_path: str, max_chars: int = 0) -> str:
        abs_path = os.path.join(self.root, rel_path.replace("/", os.sep))
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
                return content[:max_chars] if max_chars else content
        except Exception:
            return ""

    def load_workflow(self, name: str) -> str:
        content = self._read(f".agent/workflows/{name}.md")
        if not content:
            print(f"  Workflow not found: .agent/workflows/{name}.md")
        return content

    def load_common_rules(self, only: tuple[str, ...] | None = None) -> str:
        """加载公共契约。

        `only` 给出文件名前缀（如 `("00", "20")`）时只加载这几份——
        分阶段执行时研究阶段不需要质量门禁、组装阶段不需要搜索纪律，
        按需加载能省下每一轮工具循环都要重发的那几 KB。
        """
        common_dir = os.path.join(self.root, ".agent", "workflows", "common")
        if not os.path.isdir(common_dir):
            return ""

        parts = []
        for filename in sorted(os.listdir(common_dir)):
            if not filename.endswith(".md"):
                continue
            if only is not None and not filename.startswith(tuple(only)):
                continue
            content = self._read(f".agent/workflows/common/{filename}")
            if content:
                parts.append(content)
        if not parts:
            return ""
        return "\n\n---\n## Common Workflow Quality Rules\n" + "\n\n---\n".join(parts)

    def load_stage(self, rel_path: str) -> str:
        """加载阶段指令文件（相对 .agent/workflows/）。"""
        content = self._read(f".agent/workflows/{rel_path}")
        if not content:
            print(f"  Stage file not found: .agent/workflows/{rel_path}")
        return content

    def load_latest_rss(self) -> str:
        anchor_date = datetime.strptime(self._date_iso, "%Y-%m-%d")
        for delta in range(3):
            d = anchor_date - timedelta(days=delta)
            rel = f"Reports/Raw_Data/{d.strftime('%Y-%m')}/financial_data_{d.strftime('%Y%m%d')}.json"
            content = self._read(rel, max_chars=4000)
            if content:
                return f"[RSS情报 {d.strftime('%Y%m%d')}]\n{content}"
        return ""

    def build_system_instruction(
        self,
        workflow_name: str,
        stage: tuple | None = None,
        remaining_budget: int | None = None,
    ) -> str:
        """Build the system instruction from workflow content and optional RSS context.

        `stage` 为 `(阶段名, 阶段文件, 契约前缀, use_pro)` 时构建该阶段的指令：
        只装该阶段声明的公共契约，并在 workflow 正文之后追加阶段指令。
        """
        workflow = self.load_workflow(workflow_name)
        contracts = stage[2] if stage else None
        common_rules = self.load_common_rules(only=contracts)
        parts = []
        if common_rules:
            parts.append(common_rules)
            parts.append("\n\n---\n## Workflow-Specific Instructions\n")
        parts.append(workflow or f"[workflow not found: {workflow_name}]")

        if stage:
            stage_name, stage_file = stage[0], stage[1]
            stage_body = self.load_stage(stage_file)
            parts.append(
                f"\n\n---\n## 当前阶段：{stage_name}\n"
                f"本次调用**只做这一个阶段**的事。阶段之外的步骤不要提前做，也不要重复上一阶段已完成的取证。\n\n"
                + (stage_body or f"[stage file not found: {stage_file}]")
            )

        # 注入真实日期（网络时间优先，避免 Windows 时钟偏移）
        parts.append(
            f"\n\n---\n## Date Context\n"
            f"今天日期: {self._date_iso} ({self._date_compact})\n"
            f"报告文件命名和路径必须使用此日期。\n"
        )

        # 注入取证预算：与 ToolFactory 在工具层强制的是同一个数字（settings 单一真理源），
        # 提示词里写多少、代码就拦多少，不再出现「正文写 28 次、SYSTEM.md 写 8 次」的分歧。
        budget = (
            remaining_budget
            if remaining_budget is not None
            else settings.workflow_budget.for_workflow(workflow_name)
        )
        scope = "本阶段可用" if stage else "本次 workflow"
        parts.append(
            f"\n---\n## Search Budget\n"
            f"{scope}的联网取证预算为 **{budget} 点**"
            f"（search_web / browser_fetch / drill_source 各 1 点，learn_source 2 点）。\n"
            f"预算由代码强制：超出后取证工具会直接拒绝调用，你将只能用已有证据完成报告。\n"
            f"请把预算花在最关键的交叉验证上，不要用它做重复查询。\n"
        )

        if workflow_name in self.RSS_WORKFLOWS:
            rss = self.load_latest_rss()
            if rss:
                parts.append(f"\n---\n## RSS Context\n{rss}")

        return "".join(parts)


# --- The Agent ---

class ResearchAgent:
    """Workflow-oriented research agent for CLI and bot entry points."""

    # 模型分档来自 settings（可用 PRO_WORKFLOWS 环境变量覆盖）。
    # buy/sell 触碰真实下单，属高后果任务，与 deep/value 同走 Pro：
    # 一次 Pro 调用的成本增量远低于一次错误交易。
    PRO_WORKFLOWS = settings.model_routing.pro_workflows()

    def __init__(self):
        self.runner = WorkflowRunner(PROJECT_ROOT)
        self._chat_lock = threading.RLock()
        self._budget = None

        # --- Core service instances (no longer global) ---
        self.ledger = PortfolioLedger()
        self.wallet = Wallet()
        self.kill_switch = KillSwitch()
        self.guard_chain = GuardChain([
            MaxPositionGuard(ledger=self.ledger),
            CooldownGuard(ledger=self.ledger),
            ReverseCooldownGuard(ledger=self.ledger),
        ])
        self.adapter = PaperAdapter(ledger=self.ledger)
        self.execution_pipeline = ExecutionPipeline(
            ledger=self.ledger,
            wallet=self.wallet,
            guard_chain=self.guard_chain,
            adapter=self.adapter,
            kill_switch=self.kill_switch,
        )
        self.data_mgr = DataManager()
        self.data_hub = DataHub()
        self.data_hub.register(BBBrowserSource())
        self.data_hub.register(OpenCLISource())
        self.data_hub.register(YFinanceSource())
        # 跨族第二来源：腾讯/东财属交易所转发族，与 Yahoo 一系互为独立来源，
        # cross_validate_price 靠它们才可能真的「交叉」到
        self.data_hub.register(TencentQuoteSource())
        self.data_hub.register(EastmoneySource())

        # --- LLM (API-driven: google-genai SDK) ---
        self.llm = LLMClient()
        skill_path = os.path.join(PROJECT_ROOT, "Skills", "SKILL.md")
        self.llm.load_system_instruction(skill_path)
        self.llm.create_chat(tools=self._tools())

    # --- Tool functions delegated to ToolFactory ---

    # Extensions allowed for write_to_file (blocks .py, .sh, .env etc.)
    SAFE_WRITE_EXTENSIONS = ToolFactory.SAFE_WRITE_EXTENSIONS

    @staticmethod
    def _safe_resolve(base: str, user_path: str) -> str:
        """安全路径解析，防止目录遍历。"""
        return ToolFactory._safe_resolve(base, user_path)

    def _tools(self, workflow_name: str = ""):
        """Return the tool functions exposed to the model.

        `workflow_name` 为空表示自由对话（非 workflow），此时不设取证预算——
        预算是 workflow 级的约束，用户手动追问不该被工作流额度限制。
        """
        factory = ToolFactory(
            data_mgr=self.data_mgr,
            data_hub=self.data_hub,
            ledger=self.ledger,
            kill_switch=self.kill_switch,
            guard_chain=self.guard_chain,
            execution_pipeline=self.execution_pipeline,
            project_root=PROJECT_ROOT,
            budget=self._budget if workflow_name else None,
            workflow_name=workflow_name,
        )
        return factory.get_tools()

    def run_workflow(self, workflow_name: str, task: str, ticker: str = None) -> str:
        """Run a named workflow in a fresh chat session.

        多阶段工作流（见 settings.WorkflowStageSettings）按阶段串行执行：
        每个阶段是一次独立的 chat session，只装自己那部分契约与指令，
        且**不继承上一阶段的工具调用历史**——上一阶段的产出通过磁盘文件传递。
        取证预算在整个 workflow 内共享，不按阶段重置。
        """
        with self._chat_lock:
            budget_max = settings.workflow_budget.for_workflow(workflow_name)
            stages = settings.workflow_stages.stages_for(workflow_name)

            # 每轮 workflow 一份全新预算，阶段之间共享
            self._budget = BudgetManager(max_budget=budget_max)

            try:
                if stages:
                    return self._run_staged(workflow_name, task, ticker, stages, budget_max)
                return self._run_single(workflow_name, task, ticker, budget_max)
            finally:
                usage = self._budget.usage_report()
                print(
                    f"   Search budget used: {usage['consumed']}/{usage['max_budget']}"
                    f" (remaining {usage['remaining']})"
                )
                self._budget = None

    def _run_single(self, workflow_name: str, task: str, ticker: str, budget_max: int) -> str:
        use_pro = workflow_name in self.PRO_WORKFLOWS
        model_label = "Pro" if use_pro else "Flash"
        print(
            f"\nWorkflow [{workflow_name}] | Ticker: {ticker or 'N/A'} | "
            f"Model: {model_label} | Search budget: {budget_max}"
        )
        print("   Python pre-loading context...")

        system_instruction = self.runner.build_system_instruction(workflow_name)
        print(f"   Context ready ({len(system_instruction)} chars). Launching LLM...")

        result = self._chat_once(workflow_name, system_instruction, task, use_pro)
        print(f"\nWorkflow [{workflow_name}] complete.\n")
        return result

    def _run_staged(
        self, workflow_name: str, task: str, ticker: str, stages: tuple, budget_max: int
    ) -> str:
        print(
            f"\nWorkflow [{workflow_name}] | Ticker: {ticker or 'N/A'} | "
            f"Stages: {len(stages)} | Search budget: {budget_max} (shared)"
        )

        result = ""
        for index, stage in enumerate(stages, start=1):
            stage_name, _, _, stage_pro = stage
            use_pro = stage_pro and workflow_name in self.PRO_WORKFLOWS
            remaining = self._budget.remaining()
            print(
                f"\n   Stage {index}/{len(stages)} [{stage_name}] | "
                f"Model: {'Pro' if use_pro else 'Flash'} | Budget left: {remaining}"
            )

            system_instruction = self.runner.build_system_instruction(
                workflow_name, stage=stage, remaining_budget=remaining
            )
            print(f"   Context ready ({len(system_instruction)} chars). Launching LLM...")

            stage_task = self._stage_task(task, stage_name, index, len(stages), result)
            result = self._chat_once(workflow_name, system_instruction, stage_task, use_pro)

        print(f"\nWorkflow [{workflow_name}] complete ({len(stages)} stages).\n")
        return result

    @staticmethod
    def _stage_task(task: str, stage_name: str, index: int, total: int, prior: str) -> str:
        """拼装阶段任务。

        只把上一阶段的**结论文本**带下来，不带工具调用历史——
        大块中间产物应由上一阶段落盘，下一阶段用 read_file 取，
        这样上下文不会随阶段线性膨胀。
        """
        header = f"[阶段 {index}/{total}: {stage_name}]\n原始任务: {task}"
        if not prior:
            return header
        return (
            f"{header}\n\n---\n上一阶段的交接说明（工具调用历史不再保留，"
            f"需要原始数据请按其中指引 read_file 读取）：\n{prior}"
        )

    def _chat_once(self, workflow_name: str, system_instruction: str, task: str, use_pro: bool) -> str:
        """一次独立的 chat session。每次都 reset，保证阶段之间上下文隔离。"""
        self.llm.reset()
        self.llm.system_instruction = system_instruction
        self.llm.create_chat(tools=self._tools(workflow_name), use_pro=use_pro)
        return self.llm.chat(task)

    def run(self, user_input: str) -> str:
        """Run free-text input in the existing chat session."""
        with self._chat_lock:
            print(f"\nFree-text: {user_input[:80]}...")
            result = self.llm.chat(user_input)
            print("\nDone.\n")
            return result


# --- CLI Entry Point ---

def _result_has_error_prefix(result: str) -> bool:
    """Return True when a workflow surfaced an error string as its final output."""
    if not isinstance(result, str):
        return False
    stripped = result.lstrip()
    return stripped.startswith("Error:") or stripped.startswith("[Error:")

def main():
    parser = argparse.ArgumentParser(description="V3 Research System CLI")
    parser.add_argument("command", help="Command: scan, deep, quick, value, verify, add, insight, optimize, theme, push")
    parser.add_argument("args", nargs="*", help="Command arguments")
    args = parser.parse_args()

    command = args.command
    cmd_args = " ".join(args.args) if args.args else ""

    # ── push command: pure Python, no LLM needed ──
    #    push all               → push all holdings + watchlist
    #    push SPOT              → push single ticker
    #    push SPOT GOOG MA      → push multiple tickers
    if command == "push":
        from scripts.push_signals import run_push
        run_push(args.args or [])
        return

    agent = ResearchAgent()

    # (workflow_name, ticker_or_None, task_prompt)
    ticker = cmd_args.split()[0].upper() if cmd_args else None

    dispatch = {
        "scan":     ("scan",     None,   "Run the full market scan workflow and generate the report."),
        "deep":     ("deep",     ticker, f"Run deep research on {cmd_args} and generate the report.") if cmd_args else None,
        "quick":    ("quick",    ticker, f"Run a quick event review for: {cmd_args}") if cmd_args else None,
        "value":    ("value",    ticker, f"Run quality compounding analysis for {cmd_args}.") if cmd_args else None,
        "verify":   ("verify",   None,   f"Verify the following claim: {cmd_args}") if cmd_args else None,
        "add":      ("add",      None,   "Extract the latest research insights and save them to the knowledge base."),
        "update":   ("update",   ticker, f"Run a company update on {cmd_args}.") if cmd_args else None,
        "buy":      ("buy",      ticker, f"Run the buy decision workflow for {cmd_args}.") if cmd_args else None,
        "sell":     ("sell",     ticker, f"Run the sell decision workflow for {cmd_args}.") if cmd_args else None,
        "position": ("position", None,   "Run the portfolio review workflow and generate the report."),
        "rethink":  ("rethink",  ticker, f"Run a trade rethink for {cmd_args}.") if cmd_args else ("rethink", None, "Run a trade rethink."),
        "option":   ("option",   ticker, f"Run the options workflow for {cmd_args}.") if cmd_args else None,
        "macro":    ("macro",    None,   f"Run the macro workflow for: {cmd_args}") if cmd_args else ("macro", None, "Run the macro workflow."),
        "lead":     ("lead",     None,   f"Run the market lead workflow. Focus: {cmd_args}") if cmd_args else ("lead", None, "Run the market lead workflow."),
        "core":     ("core",     None,   "List currently selected core holdings and run logic check."),
        "optimize": ("optimize", None,   f"Run the portfolio optimization workflow with this input: {cmd_args}.") if cmd_args else ("optimize", None, "Run the portfolio optimization workflow."),
        "theme":    ("theme",    None,   "Run the momentum theme workflow."),
        "insight":  ("scan",     None,   "Run the market insight workflow and generate the report."),
    }

    entry = dispatch.get(command)
    if entry is None and command in dispatch:
        # command exists but requires args
        print(f"Missing arguments for command: {command}. Example: {command} NVDA")
    elif entry:
        wf_name, wf_ticker, wf_task = entry
        result = agent.run_workflow(wf_name, wf_task, ticker=wf_ticker)
        if result:
            print(result)
        if _result_has_error_prefix(result):
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        print("Available: scan, deep, quick, value, verify, add, update, buy, sell, position, rethink, option, macro, lead, core, optimize, theme, insight, push")


if __name__ == "__main__":
    try:
        main()
    except LLMConfigError as e:
        print(f"LLM 配置错误: {e}")
        sys.exit(1)
