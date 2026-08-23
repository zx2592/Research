"""
ToolFactory — 工具函数工厂

从 ResearchAgent 分离，便于独立测试。
每个方法对应一个 LLM function calling 工具，签名和 docstring 不变。
"""
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

from core import settings
from core.artifacts.schemas import OrderIntent
from core.price_consensus import build_consensus, family_of
from core.price_consensus import verify_market_cap as _verify_market_cap
from core.report_quality import ReportQualityChecker

logger = logging.getLogger(__name__)

# 分市场的财务数据来源优先级：主源 → 副源 → 一手披露。
# 主副两源用于交叉验证，对不上时以一手披露为准。
FINANCIAL_SOURCE_PRIORITY = {
    "美股": {
        "primary": "macrotrends.net/stocks/charts/{ticker}",
        "secondary": "stockanalysis.com/stocks/{ticker}/financials",
        "primary_disclosure": "SEC EDGAR 10-K / 10-Q 原文",
    },
    "港股": {
        "primary": "aastocks.com 公司基本面",
        "secondary": "macrotrends（用 ADR 代码，如 0700→TCEHY、9999→NTES）",
        "primary_disclosure": "HKEX 披露易 hkexnews.hk 年报 PDF",
    },
    "A股": {
        "primary": "东方财富结构化年报（get_financials 已直连）",
        "secondary": "巨潮资讯 cninfo.com.cn 年报原文",
        "primary_disclosure": "交易所公告 / 年报 PDF",
    },
    "台股": {
        "primary": "FinMind api.finmindtrade.com",
        "secondary": "Goodinfo goodinfo.tw",
        "primary_disclosure": "公开资讯观测站 MOPS mops.twse.com.tw",
    },
}


class ToolFactory:
    """工具函数工厂 — 从 ResearchAgent 分离，便于独立测试。"""

    SAFE_WRITE_EXTENSIONS = {".md", ".json", ".csv", ".txt", ".yaml", ".yml"}

    # 取证类工具的预算点数。非取证工具（读文件、算市值、查持仓）不计费——
    # 它们不产生外部请求，限制它们只会逼模型少做交叉验证。
    TOOL_BUDGET_COST = {
        "search_web": 1,
        "browser_fetch": 1,
        "drill_source": 1,
        "browser_operate": 1,
        "learn_source": 2,
    }

    def __init__(
        self,
        data_mgr,
        data_hub,
        ledger,
        kill_switch,
        guard_chain,
        execution_pipeline,
        project_root: str,
        budget=None,
        workflow_name: str = "",
        evidence=None,
    ):
        self.data_mgr = data_mgr
        self.data_hub = data_hub
        self.ledger = ledger
        self.kill_switch = kill_switch
        self.guard_chain = guard_chain
        self.execution_pipeline = execution_pipeline
        self.project_root = project_root
        self.report_quality_checker = ReportQualityChecker()
        self.workflow_name = workflow_name
        self.budget = budget
        self.evidence = evidence

    def _charge(self, tool_name: str) -> Optional[str]:
        """扣减取证预算。超限返回一句给模型看的指令，未超限返回 None。

        故意「软失败」而不是抛异常：预算耗尽时整轮工具循环里已经积累了大量取证结果，
        抛异常会让这一轮全部作废、下次重跑再花一遍钱。返回指令性文本能让模型就地收敛
        ——用手上已有的证据把报告写完，并在证据台账里如实标注取证已达上限。
        """
        if self.budget is None:
            return None
        cost = self.TOOL_BUDGET_COST.get(tool_name, 0)
        if cost <= 0:
            return None
        if not self.budget.can_afford(cost):
            usage = self.budget.usage_report()
            logger.warning(
                "[budget] %s blocked for workflow=%s (%s/%s used)",
                tool_name, self.workflow_name or "?", usage["consumed"], usage["max_budget"],
            )
            return (
                f"[取证预算已用尽] {tool_name} 被拒绝："
                f"本次 workflow 预算 {usage['max_budget']} 点已全部消耗。\n"
                "不要再尝试任何联网取证工具。请用已经取到的证据完成报告，"
                "并在『证据台账』中对未能取证的判断标注 [UNSOURCED]，"
                "在『质量自检』中如实写明取证已达上限。"
            )
        self.budget.consume(cost)
        return None

    def _record_evidence(self, tool_name: str, query: str, payload: str, url: str = "") -> None:
        """把一次真实取证记进证据链。

        意义不在于日志本身，而在于让「报告里声称的证据」可以和「实际取到的东西」对账。
        此前 `missing_live_tooling_evidence` 是对报告正文做正则匹配——模型只要写下
        `fetched_at` 三个字就能骗过它；有了真实记录，这个门禁才落到事实上。
        """
        if self.evidence is None:
            return
        try:
            from core.toolbus.evidence import SourceRef

            snippet = (payload or "")[:settings.search.content_truncation]
            self.evidence.record(SourceRef(
                tool_name=tool_name,
                query=str(query)[:256],
                url=url,
                snippet=snippet,
            ))
        except Exception as exc:  # 记录失败不该拖垮取证本身
            logger.warning("[evidence] failed to record %s: %s", tool_name, exc)

    def get_evidence_log(self) -> str:
        """返回本轮已经真实取到的证据清单（JSON）。
        Return the evidence actually fetched so far in this workflow.

        写『证据台账』前先调用它，按实际取到的东西填表，而不是凭记忆回想。
        每条含工具名、查询、来源 URL、摘要与抓取时间——正是台账需要的列。
        取证记录为空说明本轮一次都没取到数据，此时报告不得落盘。
        """
        if self.evidence is None:
            return json.dumps({"records": [], "note": "evidence recording not enabled"}, ensure_ascii=False)
        records = [ref.to_dict() for ref in self.evidence.sources]
        return json.dumps({"count": len(records), "records": records}, ensure_ascii=False)

    def _budget_footer(self) -> str:
        """余额紧张时附一行提示，让模型自己收敛节奏。充裕时不附，省 token。"""
        if self.budget is None:
            return ""
        remaining = self.budget.remaining()
        if remaining > 3:
            return ""
        if remaining <= 0:
            return "\n[取证预算余额: 0 — 这是最后一次取证，请开始写报告]"
        return f"\n[取证预算余额: {remaining} 点，请优先安排最关键的取证]"

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
        denied = self._charge("search_web")
        if denied:
            return denied
        result = self._do_search_web(query)
        self._record_evidence("search_web", query, result)
        return result + self._budget_footer()

    def _do_search_web(self, query: str) -> str:
        """未计费的搜索实现。计费在调用方完成，避免内部降级链路重复扣费。"""
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
        
        if self._is_research_report_path(abs_path) and ext.lower() == ".md":
            tier, expected_ticker = self._infer_report_context(abs_path)
            # 分段写入时校验「拼接后的完整报告」，而不是这一个片段。
            # 片段既不以 # 开头也不含七个章节，逐段送检必然失败——
            # 那样等于禁止分段写入，把长报告逼成一次性巨型输出。
            candidate = content
            if mode == "a":
                candidate = self._existing_text(abs_path) + content
            quality = self.report_quality_checker.check(
                candidate,
                prior_reports=self._load_related_reports(abs_path),
                tier=tier,
                expected_ticker=expected_ticker,
            )
            # 用真实取证记录覆盖基于正文正则的推测：正则只能证明报告里「写了」
            # fetched_at，证明不了真的取过数。有记录就以记录为准。
            if self.evidence is not None:
                fetched = len(self.evidence.sources)
                quality["recorded_fetches"] = fetched
                issues = quality.setdefault("issues", [])
                if fetched == 0:
                    if "missing_live_tooling_evidence" not in issues:
                        issues.append("missing_live_tooling_evidence")
                    quality["passed"] = False
                elif "missing_live_tooling_evidence" in issues:
                    # 确实取过数，只是正文没留下正则认得的痕迹——不因此拒收
                    issues.remove("missing_live_tooling_evidence")
                    quality["passed"] = not quality["missing_sections"] and not issues

            if not quality["passed"]:
                self._record_report_write_status(abs_path, False, quality)
                return (
                    "Report quality gate failed: " + json.dumps(quality, ensure_ascii=False)
                    + "\n修好上面列出的每一项后重新调用 write_to_file；不要绕过门禁写到别的路径。"
                )

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
            if self._is_research_report_path(abs_path) and ext.lower() == ".md":
                self._record_report_write_status(abs_path, True, {"passed": True, "issues": []})
                self._save_evidence_log(abs_path)
            return f"Successfully {success_action} {abs_path}"
        except Exception as e:
            return f"[File Error: {e}]"

    @staticmethod
    def _existing_text(abs_path: str) -> str:
        """读取已有内容，供分段写入时拼接校验。文件不存在按空串处理。"""
        try:
            with open(abs_path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    def _infer_report_context(self, abs_path: str) -> tuple[str, str]:
        """从报告文件名推断校验档位与预期 ticker。

        命名约定是 `YYYYMMDD_[Ticker]_[Workflow].md`（扫描类为 `YYYYMMDD_Market_Scan.md`），
        所以档位取文件名中能匹配上 workflow 名的那一段，ticker 取第二段。
        推断不出来时返回 default 档——宁可放宽，也不要因为文件名不合惯例就拒绝落盘。
        """
        stem = os.path.splitext(os.path.basename(abs_path))[0]
        parts = [p for p in stem.split("_") if p]

        tier = "default"
        tier_map = ReportQualityChecker.WORKFLOW_TIERS
        for part in parts:
            candidate = tier_map.get(part.lower())
            if candidate:
                tier = candidate
                break

        expected_ticker = ""
        if len(parts) >= 3 and parts[1].lower() not in tier_map:
            # 第二段是 Market / Core 这类栏目名时不当作 ticker
            if parts[1].lower() not in {"market", "portfolio", "position"}:
                expected_ticker = parts[1]

        return tier, expected_ticker

    def _is_research_report_path(self, abs_path: str) -> bool:
        try:
            rel = os.path.relpath(abs_path, self.project_root)
        except ValueError:
            return False
        parts = rel.replace("\\", "/").split("/")
        return len(parts) >= 2 and parts[0] == "Reports" and parts[1] != "Raw_Data"

    def _load_related_reports(self, abs_path: str) -> list[dict]:
        dirname = os.path.dirname(abs_path)
        basename = os.path.basename(abs_path)
        stem, ext = os.path.splitext(basename)
        if ext.lower() != ".md":
            return []

        parts = stem.split("_")
        if len(parts) < 3:
            return []
        ticker = parts[1]

        reports = []
        try:
            for entry in sorted(os.listdir(dirname)):
                entry_path = os.path.join(dirname, entry)
                if entry_path == abs_path or not entry.endswith(".md"):
                    continue
                entry_parts = os.path.splitext(entry)[0].split("_")
                if len(entry_parts) < 3 or entry_parts[1] != ticker:
                    continue
                try:
                    with open(entry_path, "r", encoding="utf-8") as handle:
                        reports.append({"path": entry, "content": handle.read()})
                except OSError as exc:
                    reports.append({"path": entry, "content": f"[read_error: {exc}]"})
        except OSError:
            return []
        return reports

    def _save_evidence_log(self, report_path: str) -> None:
        """把本轮真实取证记录存到报告旁边，文件名与报告同名。

        报告里的证据台账是模型写的，可能漏、可能记串；这份 JSONL 是工具层的原始记录。
        两者放在一起，事后才能把某个结论展开回它当时依据的那一页。
        """
        if self.evidence is None or not self.evidence.sources:
            return
        stem = os.path.splitext(os.path.basename(report_path))[0]
        try:
            self.evidence.output_dir = os.path.join(os.path.dirname(report_path), "evidence")
            path = self.evidence.save(stem)
            logger.info("[evidence] saved %d records to %s", len(self.evidence.sources), path)
        except OSError as exc:
            logger.warning("[evidence] failed to save log for %s: %s", report_path, exc)

    def _record_report_write_status(self, abs_path: str, passed: bool, quality: dict) -> None:
        status_path = os.path.join(self.project_root, ".codex_runtime", "report_write_status.json")
        payload = {
            "path": abs_path,
            "passed": passed,
            "quality": quality,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            os.makedirs(os.path.dirname(status_path), exist_ok=True)
            with open(status_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except OSError:
            logger.warning("Failed to record report write status: %s", status_path)

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

        denied = self._charge("browser_fetch")
        if denied:
            return denied

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
                payload = json.dumps(result.data, ensure_ascii=False)
                self._record_evidence(
                    f"browser_fetch:{engine}", f"{site} {command or ''}".strip(), payload
                )
                return payload
            except Exception as e:
                last_error = str(e)
                logger.warning("[browser_fetch] %s exception: %s", engine, last_error)
                continue

        # 降级到网页搜索仍属同一次取证，不再二次扣费
        fallback_query = self._build_browser_fallback_query(site=site, command=command, **kwargs)
        fallback_result = self._do_search_web(fallback_query)
        if fallback_result.startswith("[Error"):
            return f"[browser_fetch ERROR] Structured fetch failed. Last error: {last_error}\nWeb fallback query: {fallback_query}\n{fallback_result}"
        return (
            "[browser_fetch downgraded to web search]\n"
            f"Structured fetch failed: {last_error}\n"
            f"Web fallback query: {fallback_query}\n"
            f"{fallback_result}"
        )

    def get_realtime_quote(self, ticker: str) -> str:
        """Fetch a real-time quote for one ticker and return structured JSON."""
        symbol = (ticker or "").strip().upper()
        if not symbol:
            return json.dumps({"error": "ticker is required"}, ensure_ascii=False)

        metrics = self.data_mgr.fetch_market_prices(tickers={symbol: {"name": symbol, "type": "stock"}})
        match = next((item for item in metrics if item.get("ticker", "").upper() == symbol), None)
        if not match:
            return json.dumps({
                "ticker": symbol,
                "price": None,
                "error": "quote not found",
                "source": "fetch_market_prices",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False)

        payload = {
            "ticker": symbol,
            "name": match.get("name", symbol),
            "price": match.get("price"),
            "change_pct": match.get("change"),
            "source": "fetch_market_prices",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if "price_error" in match:
            payload["price_error"] = match["price_error"]
        encoded = json.dumps(payload, ensure_ascii=False)
        self._record_evidence("get_realtime_quote", symbol, encoded)
        return encoded

    # 取价来源：按「来源族」排布，同族再多也不构成交叉验证
    PRICE_SOURCES = ("yfinance", "tencent", "eastmoney")

    def cross_validate_price(
        self,
        ticker: str,
        tolerance_pct: float = 1.0,
        allow_identical: bool = False,
    ) -> str:
        """跨来源族交叉验证价格，返回可直接抄进报告的 `verdict` 一行。
        Cross-validate a ticker price across INDEPENDENT source families.

        `passed=True` 的条件是三个而不是一个：
        1. 至少两个**不同来源族**给出数值（腾讯/东财/新浪同属交易所转发族，
           互相比对不算交叉；Yahoo 一系属国际供应商族）；
        2. 跨族偏差 ≤ tolerance_pct；
        3. 跨族数值**不完全相同**——两个真正独立的来源几乎不可能分毫不差，
           完全相同更可能是同一份数据的两个门面（allow_identical=True 可放行）。

        未通过不是错误，是「未过项」：如实申报单源，报告照常写，
        但不得给出目标价、止损与盈亏比。
        """
        symbol = (ticker or "").strip().upper()
        if not symbol:
            return json.dumps({"error": "ticker is required"}, ensure_ascii=False)

        sources = []
        primary = json.loads(self.get_realtime_quote(symbol))
        if primary.get("price") is not None:
            sources.append({
                "source": primary.get("source", "fetch_market_prices"),
                "price": float(primary["price"]),
                "fetched_at": primary.get("fetched_at"),
            })

        for source_name in self.PRICE_SOURCES:
            if not self._source_is_available(source_name):
                continue
            try:
                result = self.data_hub.fetch(source_name=source_name, ticker=symbol, bypass_cache=True)
                data = getattr(result, "data", {}) or {}
                if data.get("price") is not None:
                    method = data.get("source_method", "datahub")
                    sources.append({
                        "source": f"{source_name}:{method}",
                        "price": float(data["price"]),
                        "fetched_at": data.get("fetched_at"),
                    })
                elif data.get("error"):
                    sources.append({"source": f"{source_name}:datahub", "error": data["error"]})
            except Exception as exc:
                sources.append({"source": f"{source_name}:datahub", "error": str(exc)})

        numeric = [item for item in sources if item.get("price") is not None]
        consensus = build_consensus(
            [
                {"source": item["source"], "value": item["price"], "fetched_at": item.get("fetched_at")}
                for item in numeric
            ],
            tolerance_pct=float(tolerance_pct),
            label="价格",
            allow_identical=allow_identical,
        )

        # 兼容旧字段：spread_pct 仍是极差口径
        spread_pct = None
        if len(numeric) >= 2:
            prices = [item["price"] for item in numeric]
            midpoint = sum(prices) / len(prices)
            if midpoint:
                spread_pct = round((max(prices) - min(prices)) / midpoint * 100, 6)

        for item in sources:
            item["family"] = family_of(item["source"])

        payload = {
            "ticker": symbol,
            "passed": consensus["passed"],
            "grade": consensus["grade"],
            "reason": consensus["reason"],
            "verdict": consensus["verdict"],
            "consensus_price": consensus["consensus"],
            "tolerance_pct": float(tolerance_pct),
            "spread_pct": spread_pct,
            "max_deviation_pct": consensus["max_deviation_pct"],
            "independent_family_count": consensus["independent_family_count"],
            "families": consensus["families"],
            "identical_values": consensus["identical_values"],
            "sources": sources,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if len(numeric) < 2:
            payload["error"] = "fewer than two price sources returned numeric prices"
        encoded = json.dumps(payload, ensure_ascii=False)
        self._record_evidence("cross_validate_price", symbol, encoded)
        return encoded

    def cross_validate_metric(
        self,
        field: str,
        values: str,
        unit: str = "",
        tolerance_pct: float = 1.0,
    ) -> str:
        """对同一个财务指标做多源交叉验证（营收 / 净利 / 毛利率 / 经营现金流…）。
        Cross-validate one financial metric across sources.

        values: JSON 字符串 `{"来源名": 数值, ...}`，例如
            '{"东方财富": 1239, "巨潮年报": 1241, "stockanalysis": 1237}'

        偏差分档：≤1% 一致取共识值；1~5% 标「存在差异」并注明两个数值与可能原因
        （GAAP/Non-GAAP、汇率、财年定义、合并口径、更新滞后）；>5% 标「重大差异」，
        必须回原始财报核实，不得直接使用。
        """
        try:
            parsed = json.loads(values) if isinstance(values, str) else dict(values or {})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return json.dumps({"error": f"values 必须是 JSON 对象 {{来源: 数值}}: {exc}"}, ensure_ascii=False)

        samples = [{"source": str(k), "value": v} for k, v in parsed.items()]
        result = build_consensus(
            samples,
            tolerance_pct=float(tolerance_pct),
            label=field or "指标",
            unit=unit,
        )
        result["field"] = field
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(result, ensure_ascii=False)
        self._record_evidence("cross_validate_metric", field, encoded)
        return encoded

    def verify_market_cap(
        self,
        price: float,
        shares: float,
        reported_cap: float,
        currency: str = "",
        tolerance_pct: float = 5.0,
    ) -> str:
        """验算市值 = 股价 × 总股本，与披露市值对照，偏差超容差即告警。
        Verify reported market cap against price × shares outstanding.

        增发、回购、库存股、ADR 存托比率都会让两者对不上——偏差超标是「回原始
        披露核实股本口径」的信号，不是四舍五入误差。
        """
        result = _verify_market_cap(
            price=price,
            shares=shares,
            reported_cap=reported_cap,
            currency=currency,
            tolerance_pct=float(tolerance_pct),
        )
        return json.dumps(result, ensure_ascii=False)

    def get_financials(self, ticker: str, years: int = 5) -> str:
        """获取结构化年度财务数据（A股走东方财富年报接口）。
        Fetch structured annual financials; A-shares via Eastmoney, others return source guidance.

        深度与估值研究里最容易出错的一步，就是从新闻正文里读营收/净利/现金流——
        口径不明、时点不明，常常还是别人算过一手的数字。能走结构化接口就不要走
        文本转述；接口覆盖不到的市场，本工具返回该市场的**来源优先级**，
        再用 `browser_fetch` / `drill_source` 回原始披露取数。
        """
        symbol = (ticker or "").strip().upper()
        if not symbol:
            return json.dumps({"error": "ticker is required"}, ensure_ascii=False)

        code = symbol.replace(".SH", "").replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
        is_a_share = code.isdigit() and len(code) == 6

        if is_a_share and self._source_is_available("eastmoney"):
            try:
                result = self.data_hub.fetch(
                    source_name="eastmoney",
                    ticker=symbol,
                    kind="financials",
                    years=int(years),
                    bypass_cache=True,
                )
                data = getattr(result, "data", {}) or {}
                data.setdefault("ticker", symbol)
                data["cross_validate_hint"] = (
                    "关键数字请再用 cross_validate_metric 与巨潮年报原文对一遍；"
                    "东方财富与其他行情站同属交易所转发族，互相比对不构成交叉。"
                )
                encoded = json.dumps(data, ensure_ascii=False)
                self._record_evidence("get_financials", symbol, encoded)
                return encoded
            except Exception as exc:
                logger.warning("[get_financials] eastmoney failed for %s: %s", symbol, exc)

        return json.dumps({
            "ticker": symbol,
            "periods": [],
            "structured_source": None,
            "note": "本市场暂无结构化接口，按下表回原始披露取数，取到后用 cross_validate_metric 交叉",
            "source_priority": FINANCIAL_SOURCE_PRIORITY,
        }, ensure_ascii=False)

    def check_report_quality(self, markdown: str, filename: str = "") -> str:
        """落盘前自检报告质量，返回 JSON 门禁结果。
        Validate a research report before saving; returns JSON gate result.

        传入 `filename`（即准备写入的报告路径）会按该报告的档位校验——
        /deep 与 /quick 的证据密度要求不同，不带 filename 时按最宽松的 default 档，
        可能出现「自检通过但 write_to_file 被拒」的落差。**务必带上 filename。**
        """
        tier, expected_ticker = ("default", "")
        if filename:
            tier, expected_ticker = self._infer_report_context(filename)
        return json.dumps(
            self.report_quality_checker.check(
                markdown, tier=tier, expected_ticker=expected_ticker
            ),
            ensure_ascii=False,
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
        denied = self._charge("browser_operate")
        if denied:
            return denied
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
        denied = self._charge("learn_source")
        if denied:
            return denied
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

        # 委派给 browser_fetch / browser_operate 的分支由被委派方自行扣费，
        # 这里只对「本方法直接发起外部请求」的分支计费，保证一次请求只扣一次。
        if source == "xueqiu":
            return self.browser_fetch(site="xueqiu", command="search", query=query)

        if source == "reddit":
            return self.browser_fetch(site="reddit", command="search", query=query)

        # New: Use operate for deep dive if a specific URL is implied or needed
        if "http" in query:
             return self.browser_operate("open", query)

        # Default: web search
        denied = self._charge("drill_source")
        if denied:
            return denied
        result = self._do_search_web(f"{query} 研报 分析")
        self._record_evidence("drill_source", query, result)
        return result + self._budget_footer()

    def get_tools(self) -> list:
        """返回工具函数列表，供 LLM function calling 使用。"""
        return [
            self.search_web,
            self.read_file,
            self.list_dir,
            self.write_to_file,
            self.get_realtime_quote,
            self.cross_validate_price,
            self.cross_validate_metric,
            self.verify_market_cap,
            self.get_financials,
            self.check_report_quality,
            self.get_evidence_log,
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
