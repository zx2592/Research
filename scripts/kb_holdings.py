"""
kb_holdings.py — 共用工具模块
==============================
供 quick_event.py / update_company.py / generate_market_scan.py 调用。
提供两个函数：
  - load_kb_context(ticker)  : 从 KB_INDEX.md 命中并读取知识卡片，返回注入 prompt 的字符串
  - load_holdings_context(ticker=None) : 从 holdings.json 读取持仓状态，返回注入 prompt 的字符串
"""

import os
import json
import re

# ========== 路径 ==========
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(_SCRIPT_DIR)
KB_INDEX_PATH = os.path.join(PROJECT_ROOT, "Memory_Layer", "Knowledge_Base", "KB_INDEX.md")
KB_DIR        = os.path.join(PROJECT_ROOT, "Memory_Layer", "Knowledge_Base")
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, "Config", "holdings.json")


# ========== 1. 知识库上下文 ==========

def load_kb_context(ticker: str) -> str:
    """
    从 KB_INDEX.md 的「检索关键词」列中查找 ticker（大小写不敏感），
    若命中则读取对应卡片文件内容，返回格式化字符串供注入 prompt。
    未命中返回空字符串。
    """
    if not ticker or not os.path.exists(KB_INDEX_PATH):
        return ""

    ticker_upper = ticker.upper()

    try:
        with open(KB_INDEX_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""

    # 解析 Markdown 表格行（跳过表头和分隔行）
    matches = []
    for line in content.splitlines():
        if not line.startswith("|") or "---" in line or "检索关键词" in line:
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) < 5:
            continue
        keywords_col = cols[0]  # 第1列：检索关键词
        card_col     = cols[4]  # 第5列：卡片路径（Markdown link）
        # 检索关键词匹配
        keywords = [kw.strip().upper() for kw in keywords_col.split(",")]
        if ticker_upper in keywords:
            # 提取 [文件名](文件名.md) 中的文件名
            m = re.search(r'\(([^)]+\.md)\)', card_col)
            if m:
                matches.append(m.group(1))

    if not matches:
        return ""

    # 读取命中的最新卡片（命中多条时取最后一条，即索引中最新的）
    card_filename = matches[-1]
    card_path = os.path.join(KB_DIR, card_filename)
    if not os.path.exists(card_path):
        return ""

    try:
        with open(card_path, "r", encoding="utf-8") as f:
            card_content = f.read()
    except Exception:
        return ""

    return f"""
## 【知识库历史档案 — {ticker_upper}】
> 以下为知识库中已有的历史研究积累，请在分析中优先引用，聚焦增量变化而非重复已知信息。

{card_content}

---
"""


# ========== 2. 持仓状态上下文 ==========

def load_holdings_context(ticker: str = None) -> str:
    """
    从 Config/holdings.json 读取持仓信息。
    - 若指定 ticker：返回该标的的持仓详情
    - 若 ticker=None：返回所有持仓的概要（供市场扫描使用）
    未找到返回空字符串。
    """
    if not os.path.exists(HOLDINGS_PATH):
        return ""

    try:
        with open(HOLDINGS_PATH, "r", encoding="utf-8") as f:
            holdings = json.load(f)
    except Exception:
        return ""

    tickers_data = holdings.get("tickers", {})
    summary      = holdings.get("summary", {})
    updated      = holdings.get("last_updated", "未知")

    if ticker:
        # 单标的查询
        ticker_upper = ticker.upper()
        info = tickers_data.get(ticker_upper)
        if not info:
            return f"\n> 📋 **持仓状态（{ticker_upper}）**: 当前未持有 / 观察池\n"
        cost = info.get("cost_basis_usd", 0)
        avg  = info.get("avg_cost_usd", 0)
        stg  = info.get("strategy", "未知")
        sec  = info.get("sector", "未知")
        return f"""
## 【持仓状态 — {ticker_upper}】（数据截至 {updated}）
- **策略分类**: {stg}
- **板块**: {sec}
- **持仓成本**: ${cost:,.0f}（均价 ${avg:.2f}）
- **持仓账户**: {', '.join(info.get('accounts', []))}
- **含期权**: {'是' if info.get('has_options') else '否'}

"""
    else:
        # 全量持仓概要（市场扫描用）
        alloc = summary.get("allocation", {})
        total = summary.get("total_cost_basis_usd", 0)

        lines = [
            f"\n## 【当前持仓概要】（数据截至 {updated}，总成本 ${total:,.0f}）",
            "",
            "| 策略分类 | 金额（USD） | 占比 |",
            "| :--- | ---: | ---: |",
        ]
        for cat, data in alloc.items():
            lines.append(f"| {cat} | ${data.get('value', 0):,.0f} | {data.get('pct', 0)}% |")

        lines.append("")
        lines.append("**核心持仓标的**（按成本降序）:")
        sorted_tickers = sorted(tickers_data.items(),
                                key=lambda x: -x[1].get("cost_basis_usd", 0))
        for sym, info in sorted_tickers[:15]:
            stg  = info.get("strategy", "?")
            cost = info.get("cost_basis_usd", 0)
            lines.append(f"- **{sym}** ({stg}): ${cost:,.0f}")

        lines.append("")
        return "\n".join(lines)
