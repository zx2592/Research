"""
ToolFactory — 工具函数工厂

从 ResearchAgent 分离，便于独立测试。
每个方法对应一个 LLM function calling 工具，签名和 docstring 不变。
"""
import json
import logging
import os
import subprocess
from typing import Optional

from core import settings
from core.artifacts.schemas import OrderIntent

logger = logging.getLogger(__name__)


class ToolFactory:
    """工具函数工厂 — 从 ResearchAgent 分离，便于独立测试。"""

    SAFE_WRITE_EXTENSIONS = {".md", ".json", ".csv", ".txt", ".yaml", ".yml"}

    def __init__(self, data_mgr, data_hub, ledger, kill_switch, guard_chain, execution_pipeline, project_root: str):
        self.data_mgr = data_mgr
        self.data_hub = data_hub
        self.ledger = ledger
        self.kill_switch = kill_switch
        self.guard_chain = guard_chain
        self.execution_pipeline = execution_pipeline
        self.project_root = project_root

    @staticmethod
    def _safe_resolve(base: str, user_path: str) -> str:
        """安全路径解析，防止目录遍历。"""
        if os.path.isabs(user_path):
            resolved = os.path.normpath(user_path)
        else:
            resolved = os.path.normpath(os.path.join(base, user_path))
        
        base_resolved = os.path.normpath(base)
        
        # Windows 路径不区分大小写，需要统一转换后对比，防止 d:\ vs D:\ 导致误判越界
        if os.name == 'nt':
            if not resolved.lower().startswith(base_resolved.lower() + os.sep) and resolved.lower() != base_resolved.lower():
                raise ValueError(f"路径越界被拒绝 (Windows): {user_path}")
        else:
            if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
                raise ValueError(f"路径越界被拒绝: {user_path}")
                
        return resolved

    def search_web(self, query: str) -> str:
        """搜索互联网获取最新信息。Search the web for latest information."""
        result = self.data_mgr.search_web(query)
        if "配额已用完" in result or "搜索错误" in result:
            brave = self.data_mgr.search_brave(query)
            if not brave.startswith("[Error"):
                return brave + "\n[来源: Brave Search 降级]"
        return result

    def read_file(self, filepath: str) -> str:
        """读取项目文件内容（支持相对路径，基于项目根目录）。
        Read a file. Relative paths are resolved from the project root.
        Use this to read workflow files, config files, reports, and knowledge base entries.
        """
        try:
            abs_path = self._safe_resolve(self.project_root, filepath)
        except ValueError as e:
            return f"[Access denied: {e}]"
        logger.info("Reading: %s", abs_path)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"[File not found: {filepath}]"
        except Exception as e:
            return f"[Error reading {filepath}: {e}]"

    def list_dir(self, path: str) -> str:
        """列出目录下的文件和子目录（支持相对路径，基于项目根目录）。
        List files and subdirectories. Relative paths are resolved from the project root.
        """
        try:
            abs_path = self._safe_resolve(self.project_root, path)
        except ValueError as e:
            return f"[Access denied: {e}]"
        logger.info("Listing: %s", abs_path)
        try:
            entries = sorted(os.listdir(abs_path))
            lines = []
            for entry in entries:
                full = os.path.join(abs_path, entry)
                tag = "[DIR] " if os.path.isdir(full) else "      "
                lines.append(f"{tag}{entry}")
            return "\n".join(lines) if lines else "(empty directory)"
        except FileNotFoundError:
            return f"[Directory not found: {path}]"
        except Exception as e:
            return f"[Error listing {path}: {e}]"

    def write_to_file(self, filename: str, content: str, mode: str = "w") -> str:
        """将内容写入文件（支持相对路径，基于项目根目录）。
        Write content to a file. Relative paths are resolved from the project root.
        'mode' can be 'w' (overwrite) or 'a' (append).
        """
        try:
            abs_path = self._safe_resolve(self.project_root, filename)
        except ValueError as e:
            return f"[Access denied: {e}]"
        _, ext = os.path.splitext(abs_path)
        if ext.lower() not in self.SAFE_WRITE_EXTENSIONS:
            return f"[写入被拒绝: 不允许写入 {ext} 文件，仅支持 {', '.join(sorted(self.SAFE_WRITE_EXTENSIONS))}]"
        
        file_mode = "a" if mode == "a" else "w"
        action = "Appending to" if file_mode == "a" else "Saving to"
        success_action = "appended to" if file_mode == "a" else "saved to"
        logger.info("%s: %s", action, abs_path)
        
        try:
            parent = os.path.dirname(abs_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, file_mode, encoding="utf-8") as f:
                f.write(content)
            return f"Successfully {success_action} {abs_path}"
        except Exception as e:
            return f"[File Error: {e}]"

    def execute_python_script(self, script_path: str, args: str = "") -> str:
        """运行指定的 Python 脚本并返回输出。Run a python script."""
        try:
            resolved = self._safe_resolve(self.project_root, script_path)
        except ValueError as e:
            return f"[安全拒绝] {e}"
        if not resolved.lower().endswith(".py"):
            return "[安全拒绝] 仅允许执行 .py 文件"
        logger.info("执行脚本: %s %s", resolved, args)
        try:
            cmd = ["python", resolved]
            if args:
                cmd.extend(args.split())
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=120,
            )
            return result.stdout if result.returncode == 0 else f"Error {result.returncode}: {result.stderr}"
        except Exception as e:
            return f"Execution Failed: {e}"

    def _get_registered_source(self, source_name: str):
        """Return a registered DataHub source when available."""
        sources = getattr(self.data_hub, "_sources", {})
        if isinstance(sources, dict):
            return sources.get(source_name)
        return None

    def _source_is_available(self, source_name: str) -> bool:
        """Treat missing or explicitly unavailable adapters as unusable."""
        source = self._get_registered_source(source_name)
        if source is None:
            return False
        return getattr(source, "available", True)

    @staticmethod
    def _build_browser_fallback_query(site: str, command: str = None, **kwargs) -> str:
        """Convert a structured browser fetch request into a plain web query."""
        parts = [site]
        if command:
            parts.append(command)

        for key, value in kwargs.items():
            if value in (None, "", False):
                continue
            if isinstance(value, (list, tuple, set)):
                value = " ".join(str(item) for item in value if item is not None)
            label = key.replace("_", " ")
            if value is True:
                parts.append(label)
            else:
                parts.append(f"{label} {value}")

        return " ".join(str(part) for part in parts if part).strip()

    def browser_fetch(self, site: str, command: str = None, source: str = "opencli", **kwargs) -> str:
        """
        使用真实浏览器获取高质量结构化数据 (xueqiu, zhihu, twitter 等)。
        'opencli' 为推荐的数据抓取引擎；'bb-browser' 用于基础指令。

        Fallback Logic:
        Prefer opencli first, then try any available structured backup.
        If all structured engines fail, degrade to standard web search.
        """
        logger.info("[browser_fetch] %s | %s %s", source, site, command or "")

        engines_to_try = []
        if self._source_is_available(source):
            engines_to_try.append(source)
        elif source != "opencli":
            logger.warning("[browser_fetch] requested source unavailable: %s", source)

        if source == "opencli" and self._source_is_available("bb-browser") and "bb-browser" not in engines_to_try:
            engines_to_try.append("bb-browser")

        last_error = "Unknown error"
        for engine in engines_to_try:
            try:
                result = self.data_hub.fetch(source_name=engine, site=site, command=command, **kwargs)
                if isinstance(result.data, dict) and "error" in result.data:
                    last_error = result.data["error"]
                    logger.warning("[browser_fetch] %s failed: %s", engine, last_error)
                    continue
                return json.dumps(result.data, ensure_ascii=False)
            except Exception as e:
                last_error = str(e)
                logger.warning("[browser_fetch] %s exception: %s", engine, last_error)
                continue

        fallback_query = self._build_browser_fallback_query(site=site, command=command, **kwargs)
        fallback_result = self.search_web(fallback_query)
        if fallback_result.startswith("[Error"):
            return f"[browser_fetch ERROR] Structured fetch failed. Last error: {last_error}\nWeb fallback query: {fallback_query}\n{fallback_result}"
        return (
            "[browser_fetch downgraded to web search]\n"
            f"Structured fetch failed: {last_error}\n"
            f"Web fallback query: {fallback_query}\n"
            f"{fallback_result}"
        )

    def get_portfolio_snapshot(self) -> str:
        """获取当前投资组合的所有持仓快照（含成本、股数、市值）。Get real-time portfolio holdings."""
        logger.info("Fetching portfolio snapshot...")
        current_prices = {}
        metrics = self.data_mgr.fetch_market_prices(tickers=None)
        for m in metrics:
            if 'price' in m:
                current_prices[m['ticker']] = m['price']
        snapshot = self.ledger.current_snapshot(prices=current_prices)
        return json.dumps(snapshot.to_dict(), ensure_ascii=False)

    def preview_trade(self, ticker: str, side: str, quantity: float, price: float) -> str:
        """风控预览：检查某笔即将发生的订单是否触碰红线（如仓位超上限）。Preview an order for risk compliance."""
        logger.info("Guard check: %s %s %s @ %s", side.upper(), quantity, ticker, price)
        try:
            intent = OrderIntent(
                ticker=ticker,
                side=side.lower(),
                quantity=quantity,
                order_type="limit",
                limit_price=price,
                rationale="preview",
                confidence=settings.execution.preview_confidence,
            )
        except ValueError as e:
            return f"Denied: {e}"
        current_prices = {ticker: price}

        if self.kill_switch.is_active():
            status = self.kill_switch.status()
            return f"Denied: KillSwitch is active: {status.get('reason')}"

        result = self.guard_chain.run(intent, current_prices)
        if not result.passed:
            return f"Denied by Guard: {result.reason}"
        return "Passed: Trade complies with all risk limits."

    def execute_trade(self, ticker: str, side: str, quantity: float, order_type: str, limit_price: float, rationale: str) -> str:
        """正式确认！提交订单到执行管线并落账。Submit an order to execution pipeline and record the trade."""
        logger.info("Executing Trade: %s %s %s @ %s", side.upper(), quantity, ticker, limit_price)
        try:
            intent = OrderIntent(
                ticker=ticker,
                side=side.lower(),
                quantity=float(quantity),
                order_type=order_type,
                limit_price=float(limit_price),
                rationale=rationale,
                confidence=settings.execution.default_confidence,
            )
        except ValueError as e:
            return f"Execution Pipeline Rejected: {e}"
        current_prices = {ticker: limit_price}
        try:
            fill = self.execution_pipeline.execute(intent, prices=current_prices, message=f"Triggered by user via Assistant: {rationale}")
            logger.info("Trade Filled! Commit hash: %s", fill.get('commit_hash'))
            return json.dumps(fill, ensure_ascii=False)
        except Exception as e:
            logger.error("execution rejected: %s", e)
            return f"Execution Pipeline Rejected: {e}"

    def browser_operate(self, action: str, *args) -> str:
        """使用浏览器自动化执行高级操作 (open, click, type, screenshot, eval, scroll, network)。
        Advanced browser automation via opencli.
        
        Examples:
          - browser_operate("open", "https://xyz.com")
          - browser_operate("screenshot")
          - browser_operate("eval", "document.title")
        """
        logger.info("[browser_operate] Action: %s", action)
        try:
            result = self.data_hub.operate(source_name="opencli", action=action, *args)
            return json.dumps(result.data, ensure_ascii=False)
        except Exception as e:
            return f"[browser_operate ERROR] {e}"

    def system_doctor(self) -> str:
        """诊断系统连通性（检查浏览器插件和 daemon 状态）。Diagnose system connectivity."""
        logger.info("[system_doctor] Checking connectivity...")
        try:
            result = self.data_hub.doctor(source_name="opencli")
            return json.dumps(result.data, ensure_ascii=False)
        except Exception as e:
            return f"[system_doctor ERROR] {e}"

    def learn_source(self, url: str, goal: str = "search") -> str:
        """自动探索并生成新站点的适配器。Automatically explore and generate a new site adapter.
        
        Args:
           url: 目标站点 URL
           goal: 抓取目标 (默认为 search)
        """
        logger.info("[learn_source] URL: %s Goal: %s", url, goal)
        try:
            # Using basic subprocess to call opencli generate
            cmd = ["opencli", "generate", url, "--goal", goal]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=180,
                shell=True,
            )
            return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
        except Exception as e:
            return f"[learn_source ERROR] {e}"

    def drill_source(self, source: str, query: str) -> str:
        """对投资线索的来源网站进行追问式深度搜集。
        Drill into the original source site for deeper information on an investment lead.

        source: 来源标识 — "xueqiu" | "reddit" | "web"
        query: 追问关键词、ticker 或具体问题

        路由:
          - xueqiu    → opencli xueqiu search [query]
          - reddit    → opencli reddit search [query]
          - web       → search_web 通用搜索 (fallback to browser_operate if needed)
        """
        logger.info("[drill_source] source=%s query=%s", source, query)

        if source == "xueqiu":
            return self.browser_fetch(site="xueqiu", command="search", query=query)

        if source == "reddit":
            return self.browser_fetch(site="reddit", command="search", query=query)

        # New: Use operate for deep dive if a specific URL is implied or needed
        if "http" in query:
             return self.browser_operate("open", query)

        # Default: web search
        return self.data_mgr.search_web(f"{query} 研报 分析")

    def get_tools(self) -> list:
        """返回工具函数列表，供 LLM function calling 使用。"""
        return [
            self.search_web,
            self.read_file,
            self.list_dir,
            self.write_to_file,
            self.get_portfolio_snapshot,
            self.preview_trade,
            self.execute_trade,
            self.execute_python_script,
            self.browser_fetch,
            self.drill_source,
            self.browser_operate,
            self.system_doctor,
            self.learn_source,
        ]
