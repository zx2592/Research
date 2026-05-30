import sys
import os
import json
from datetime import datetime

# 导入项目模块
sys.path.append(os.getcwd())

from services.portfolio.ledger import PortfolioLedger
from parse_positions import build_summary, write_json, write_md, load_previous_extra_cash

def sync():
    ledger = PortfolioLedger()
    snapshot = ledger.current_snapshot()
    
    # 将 snapshot 转回 aggregated_positions 格式供 parse_positions 的逻辑使用
    # aggregated: {(symbol, sec_type): {position, value_usd, accounts}}
    aggregated = {}
    for pos in snapshot.positions:
        # 假设全是 STK，账户设为占位 ACCOUNT_ID (由于 ledger 没存 sec_type，我们根据代码后缀或默认值判断)
        sec_type = "STK"
        # snapshot 的 avg_cost 是 USD (如果 ledger 存的是 HKD 且没做汇率转换，这里会有偏差)
        # 暂时系统内部逻辑假设金额单位一致，或者由 enrich_with_prices 处理
        key = (pos.ticker, sec_type)
        aggregated[key] = {
            "position": pos.shares,
            "value_usd": pos.cost_basis, # 这里是成本
            "accounts": {"ACCOUNT_ID"}
        }
    
    extra_cash = load_previous_extra_cash()
    summary, tickers = build_summary(aggregated, extra_cash)
    
    print("Syncing Ledger data to holdings summary...")
    write_json("Ledger (Manual Sync)", extra_cash, summary, tickers)
    write_md(summary, tickers, extra_cash)
    print("Done. Config/我的持仓.md has been refreshed from the SQL ledger.")

if __name__ == "__main__":
    sync()
