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
from core.network_time import get_network_date
from services.portfolio.ledger import PortfolioLedger
from services.execution.pipeline import ExecutionPipeline
from services.execution.wallet import Wallet
from services.execution.guards import GuardChain, MaxPositionGuard, CooldownGuard, ReverseCooldownGuard
from services.execution.kill_switch import KillSwitch
from services.execution.adapters.paper import PaperAdapter
from services.datahub.hub import DataHub
from services.datahub.sources import BBBrowserSource, OpenCLISource


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

    def load_latest_rss(self) -> str:
        anchor_date = datetime.strptime(self._date_iso, "%Y-%m-%d")
        for delta in range(3):
            d = anchor_date - timedelta(days=delta)
            rel = f"Reports/Raw_Data/{d.strftime('%Y-%m')}/financial_data_{d.strftime('%Y%m%d')}.json"
            content = self._read(rel, max_chars=4000)
            if content:
                return f"[RSS情报 {d.strftime('%Y%m%d')}]\n{content}"
        return ""

    def build_system_instruction(self, workflow_name: str) -> str:
        """Build the system instruction from workflow content and optional RSS context."""
        workflow = self.load_workflow(workflow_name)
        parts = [workflow or f"[workflow not found: {workflow_name}]"]

        # 注入真实日期（网络时间优先，避免 Windows 时钟偏移）
        parts.append(
            f"\n\n---\n## Date Context\n"
            f"今天日期: {self._date_iso} ({self._date_compact})\n"
            f"报告文件命名和路径必须使用此日期。\n"
        )

        if workflow_name in self.RSS_WORKFLOWS:
            rss = self.load_latest_rss()
            if rss:
                parts.append(f"\n---\n## RSS Context\n{rss}")

        return "".join(parts)


# --- The Agent ---

class ResearchAgent:
    """Workflow-oriented research agent for CLI and bot entry points."""

    PRO_WORKFLOWS = frozenset({"deep", "value", "verify"})

    def __init__(self):
        self.runner = WorkflowRunner(PROJECT_ROOT)
        self._chat_lock = threading.RLock()

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

    def _tools(self):
        """Return the tool functions exposed to the model."""
        factory = ToolFactory(
            data_mgr=self.data_mgr,
            data_hub=self.data_hub,
            ledger=self.ledger,
            kill_switch=self.kill_switch,
            guard_chain=self.guard_chain,
            execution_pipeline=self.execution_pipeline,
            project_root=PROJECT_ROOT,
        )
        return factory.get_tools()

    def run_workflow(self, workflow_name: str, task: str, ticker: str = None) -> str:
        """Run a named workflow in a fresh chat session."""
        with self._chat_lock:
            use_pro = workflow_name in self.PRO_WORKFLOWS
            model_label = "Pro" if use_pro else "Flash"
            print(f"\nWorkflow [{workflow_name}] | Ticker: {ticker or 'N/A'} | Model: {model_label}")
            print("   Python pre-loading context...")

            system_instruction = self.runner.build_system_instruction(workflow_name)

            print(f"   Context ready ({len(system_instruction)} chars). Launching LLM...")

            # 每次 workflow 创建新的独立 session（兼容 VPS 和桌面模式）
            self.llm.reset()
            self.llm.system_instruction = system_instruction
            self.llm.create_chat(tools=self._tools(), use_pro=use_pro)

            result = self.llm.chat(task)
            print(f"\nWorkflow [{workflow_name}] complete.\n")
            return result

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
