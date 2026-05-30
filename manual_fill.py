import sys
import os

# 确保可以导入项目模块
sys.path.append(os.getcwd())

try:
    from services.portfolio.ledger import PortfolioLedger
    from services.portfolio.events import FillEvent

    ledger = PortfolioLedger()

    # 示例：手动向账本补录一笔成交（请替换为你自己的标的/数量/价格/账户）
    event = FillEvent(
        ticker="TICKER",          # 例如 "NVDA" 或 "0700.HK"
        side="buy",
        quantity=100.0,
        price=100.0,
        commission=1.0,
        account="ACCOUNT_ID",      # 你的券商账户标识
        order_intent_id="manual_example_buy"
    )

    ledger.emit(event)
    print(f"Successfully recorded {event.ticker} buy in ledger: {event.quantity} shares @ {event.price}.")

except Exception as e:
    print(f"Error recording fill: {e}")
