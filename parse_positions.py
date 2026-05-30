#!/usr/bin/env python3
"""
parse_positions.py — 持仓数据解析器 (升级版)
========================================
功能：
  1. 读取 IB 导出的 CSV 文件（Account/Symbol/SecType/Currency/Position/AvgCost）
  2. 解析并汇总各标的的成本/策略/板块分类
  3. 将结果写入 Config/holdings.json（单一真相来源，供所有脚本和工作流读取）
  4. 同步重写 Config/我的持仓.md（Markdown 表格，供人类阅读）
  5. 终端打印汇总信息

用法：
  python parse_positions.py [csv_path] [--extra-cash AMOUNT]

  csv_path     : 可选。IB 导出 CSV 路径，默认为 "position update.csv"（相对项目根目录）
  --extra-cash : 可选。额外现金余额（USD）。若不指定，沿用上次 holdings.json 中存储的值；
                 首次运行时需要指定，例如 --extra-cash 263000

示例：
  # 现金不变，只更新持仓：
  python parse_positions.py "position update.csv"

  # 现金变了，同步更新：
  python parse_positions.py "position update.csv" --extra-cash 285000
"""

import csv
import sys
import json
import os
import argparse
from datetime import datetime
from collections import defaultdict

# ========== 路径配置 ==========
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HOLDINGS_JSON = os.path.join(PROJECT_ROOT, "Config", "holdings.json")
HOLDINGS_MD   = os.path.join(PROJECT_ROOT, "Config", "我的持仓.md")

# ========== 分类规则（可维护——请按自己的组合自定义）==========
# 下方为示例占位，标记哪些标的归为「长期核心」与「现金/收益」。
LONG_TERM_TICKERS = {"TICKER_A", "TICKER_B"}
CASH_TICKERS      = {"BIL"}

# ticker → 板块 的分类查找表（示例规则，可按需扩充）。
SECTOR_MAP = {
    frozenset({"IBIT", "ARKB", "BITB", "ETHA", "COIN"}): "Crypto/Commodities",
    frozenset({"V", "MA", "HOOD", "SOFI"}):              "Fintech/Financials",
    frozenset({"GOOG", "MSFT", "NVDA"}):                 "Tech/Internet",
    frozenset({"EWY", "MCHI", "EWJ"}):                   "Asia Equities",
}

def get_sector(symbol: str) -> str:
    for tickers, sector in SECTOR_MAP.items():
        if symbol in tickers:
            return sector
    return "Other"

def get_strategy(symbol: str) -> str:
    if symbol in LONG_TERM_TICKERS:
        return "Long-Term Core"
    if symbol in CASH_TICKERS:
        return "Cash/Yield"
    return "Short-Term Satellite"

# ========== 读取上次 extra_cash（若有）==========
def load_previous_extra_cash() -> float:
    if os.path.exists(HOLDINGS_JSON):
        try:
            with open(HOLDINGS_JSON, "r", encoding="utf-8") as f:
                prev = json.load(f)
            return float(prev.get("extra_cash_usd", 0.0))
        except Exception:
            pass
    return 0.0

# ========== 解析 CSV ==========
def parse_csv(file_path: str) -> dict:
    """返回 aggregated_positions: {(symbol, sec_type): {position, value_usd, accounts}}"""
    aggregated = defaultdict(lambda: {"position": 0.0, "value_usd": 0.0, "accounts": set()})
    accounts_seen = set()

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            account  = row["Account"]
            symbol   = row["Symbol"]
            sec_type = row["SecType"]
            currency = row["Currency"]
            try:
                position = float(row["Position"])
                avg_cost = float(row["AvgCost"])
            except ValueError:
                continue

            # 跳过非 USD（如 JPY 套利仓）
            if currency != "USD":
                continue

            accounts_seen.add(account)
            value = abs(position * avg_cost)
            key = (symbol, sec_type)
            aggregated[key]["position"] += position
            aggregated[key]["value_usd"] += value
            aggregated[key]["accounts"].add(account)

    return aggregated, accounts_seen

# ========== 构建汇总数据 ==========
def build_summary(aggregated: dict, extra_cash: float) -> dict:
    tickers = {}
    status_total  = defaultdict(float)
    sector_total  = defaultdict(float)
    total_cost    = extra_cash

    # 现金单独计入
    status_total["Cash/Yield"] += extra_cash

    for (symbol, sec_type), data in aggregated.items():
        value    = data["value_usd"]
        strategy = get_strategy(symbol)
        sector   = get_sector(symbol)

        total_cost          += value
        status_total[strategy] += value
        sector_total[sector]   += value

        avg_cost_per_share = (value / abs(data["position"])) if data["position"] != 0 else 0.0
        shares = data["position"]

        if symbol not in tickers:
            tickers[symbol] = {
                "strategy":       strategy,
                "sector":         sector,
                "total_shares":   0.0,
                "avg_cost_usd":   avg_cost_per_share,
                "cost_basis_usd": 0.0,
                "has_options":    False,
                "accounts":       list(data["accounts"]),
                "positions":      []
            }

        tickers[symbol]["cost_basis_usd"] += value
        tickers[symbol]["total_shares"]   += shares
        tickers[symbol]["has_options"]    = tickers[symbol]["has_options"] or (sec_type == "OPT")
        tickers[symbol]["positions"].append({"type": sec_type, "shares": shares, "value": value})

        # 更新加权均价（仅股票类型）
        if sec_type == "STK":
            tickers[symbol]["avg_cost_usd"] = avg_cost_per_share

    # 计算各分类百分比
    def pct_dict(d):
        return {k: {"value": round(v, 2), "pct": round(v / total_cost * 100, 1) if total_cost else 0}
                for k, v in d.items()}

    return {
        "total_cost_basis_usd": round(total_cost, 2),
        "allocation": pct_dict(status_total),
        "by_sector":  pct_dict(sector_total),
    }, tickers

# ========== 写出 holdings.json ==========
def write_json(csv_source: str, extra_cash: float, summary: dict, tickers: dict):
    # 将 accounts 的 set 转成 list（JSON 可序列化）
    serializable_tickers = {}
    for sym, data in tickers.items():
        t = dict(data)
        t["accounts"] = list(t["accounts"]) if isinstance(t["accounts"], set) else t["accounts"]
        serializable_tickers[sym] = t

    payload = {
        "last_updated":   datetime.now().strftime("%Y-%m-%d"),
        "csv_source":     os.path.basename(csv_source),
        "extra_cash_usd": extra_cash,
        "summary":        summary,
        "tickers":        serializable_tickers,
        "long_term_tickers": sorted(LONG_TERM_TICKERS),
        "cash_tickers":      sorted(CASH_TICKERS),
    }
    os.makedirs(os.path.dirname(HOLDINGS_JSON), exist_ok=True)
    with open(HOLDINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=list)
    print(f"  [OK] holdings.json 已写出: {HOLDINGS_JSON}")

# ========== 重写 Config/我的持仓.md ==========
def write_md(summary: dict, tickers: dict, extra_cash: float):
    today     = datetime.now().strftime("%Y-%m-%d")
    total_usd = summary["total_cost_basis_usd"]

    lines = [
        "# 我的持仓",
        "",
        f"> **最后更新**: {today} | **数据来源**: `Config/holdings.json`（由 `parse_positions.py` 自动生成）",
        f"> ⚠️ **请勿手动编辑此文件**——重新运行 `parse_positions.py` 后会被覆盖。",
        "",
        "---",
        "",
        "## 💼 持仓总览",
        "",
        f"**组合总成本（USD）**: ${total_usd:,.0f}",
        "",
        "| 分类 | 金额（USD） | 占比 |",
        "| :--- | ---: | ---: |",
    ]
    # 仓位分类
    for category, data in summary["allocation"].items():
        lines.append(f"| {category} | ${data['value']:,.0f} | {data['pct']}% |")
    if extra_cash > 0:
        lines.append(f"| *(含场外现金)* | *${extra_cash:,.0f}* | — |")

    lines += ["", "---", "", "## 📈 持仓明细", ""]

    # 按分类分组
    categories_order = ["Long-Term Core", "Short-Term Satellite", "Cash/Yield", "Other"]
    by_cat = defaultdict(list)
    sorted_tickers = sorted(tickers.items(), key=lambda x: -x[1]["cost_basis_usd"])
    for sym, data in sorted_tickers:
        by_cat[data["strategy"]].append((sym, data))

    for cat in categories_order:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| 代码 | 板块 | 成本（USD） | 占比 | 股票股数 | 含期权 |")
        lines.append("| :--- | :--- | ---: | ---: | ---: | :---: |")
        for sym, data in items:
            has_opt   = "Yes" if data.get("has_options") else "-"
            stk_shares = sum(p["shares"] for p in data.get("positions", []) if p["type"] == "STK")
            pct       = round(data["cost_basis_usd"] / total_usd * 100, 1) if total_usd else 0
            lines.append(f"| **{sym}** | {data['sector']} | ${data['cost_basis_usd']:,.0f} | {pct}% | {stk_shares:,.0f} | {has_opt} |")
        lines.append("")

    lines += [
        "---",
        "",
        "## 📊 板块分布",
        "",
        "| 板块 | 金额（USD） | 占比 |",
        "| :--- | ---: | ---: |",
    ]
    for sector, data in sorted(summary["by_sector"].items(), key=lambda x: -x[1]["value"]):
        lines.append(f"| {sector} | ${data['value']:,.0f} | {data['pct']}% |")

    with open(HOLDINGS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  [OK] 我的持仓.md 已更新: {HOLDINGS_MD}")

# ========== 终端汇总打印 ==========
def print_summary(accounts_seen, summary, tickers, extra_cash):
    total = summary["total_cost_basis_usd"]
    print(f"\n账户: {', '.join(sorted(accounts_seen))}")
    if extra_cash > 0:
        print(f"场外现金（手动）: ${extra_cash:,.0f}")
    print(f"\n--- 仓位分类（含现金）---")
    for k, v in summary["allocation"].items():
        print(f"  {k}: ${v['value']:,.0f} ({v['pct']}%)")
    print(f"\n--- 板块分布 ---")
    for k, v in sorted(summary["by_sector"].items(), key=lambda x: -x[1]["value"]):
        print(f"  {k}: ${v['value']:,.0f} ({v['pct']}%)")
    print(f"\n总成本代理（USD）: ${total:,.0f}")
    print(f"\n--- 持仓前15（按成本降序）---")
    top15 = sorted(tickers.items(), key=lambda x: -x[1]["cost_basis_usd"])[:15]
    for sym, data in top15:
        accts = ",".join(data["accounts"])
        print(f"  {sym}: ${data['cost_basis_usd']:,.0f} | {data['strategy']} | {data['sector']} [{accts}]")

# ========== 主流程 ==========
def main():
    parser = argparse.ArgumentParser(description="解析 IB 持仓 CSV，生成 holdings.json 和 我的持仓.md")
    parser.add_argument("csv_path", nargs="?",
                        default=os.path.join(PROJECT_ROOT, "position update.csv"),
                        help="IB 导出 CSV 路径（默认: 项目根目录下的 'position update.csv'）")
    parser.add_argument("--extra-cash", type=float, default=None,
                        help="额外现金余额（USD）。不指定时沿用上次 holdings.json 中的值")
    args = parser.parse_args()

    # 确定现金金额
    if args.extra_cash is not None:
        extra_cash = args.extra_cash
        print(f"💰 额外现金（命令行指定）: ${extra_cash:,.0f}")
    else:
        extra_cash = load_previous_extra_cash()
        if extra_cash > 0:
            print(f"💰 额外现金（沿用上次）: ${extra_cash:,.0f}")
        else:
            print("⚠️  未找到上次现金记录，现金为 $0。如需设置请用 --extra-cash 参数。")

    csv_path = args.csv_path
    if not os.path.exists(csv_path):
        print(f"❌ 找不到 CSV 文件: {csv_path}")
        sys.exit(1)

    print(f"\n📂 解析文件: {csv_path}")
    aggregated, accounts_seen = parse_csv(csv_path)

    summary, tickers = build_summary(aggregated, extra_cash)

    print_summary(accounts_seen, summary, tickers, extra_cash)

    print("\n📝 写出文件...")
    write_json(csv_path, extra_cash, summary, tickers)
    write_md(summary, tickers, extra_cash)

    print("\n✅ 完成。所有工作流现在读取 Config/holdings.json 作为持仓数据来源。")

if __name__ == "__main__":
    main()
