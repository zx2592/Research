import yfinance as yf
import akshare as ak
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MarketDataFetcher:
    def __init__(self, config):
        self.config = config

    def get_price_snapshot(self, symbol, market='us'):
        """
        Get current price and % change.
        """
        try:
            if market == 'us':
                ticker = yf.Ticker(symbol)
                # fast_info is often faster than history(period='1d')
                price = ticker.fast_info.last_price
                prev_close = ticker.fast_info.previous_close
                if price and prev_close:
                    pct_change = ((price - prev_close) / prev_close) * 100
                    return {'price': price, 'pct_change': pct_change}
            
            elif market == 'cn':
                # Akshare for A-shares
                # symbol format in akshare might be different, e.g., sh600519
                # Assuming symbol is 6-digit code, let's try generic A-share spot
                # This could be slow if doing one by one. Better to bulk fetch if possible.
                # For simplicity, using simple individual fetch or a broad market scan if needed.
                df = ak.stock_zh_a_spot_em()
                row = df[df['代码'] == symbol]
                if not row.empty:
                    price = row.iloc[0]['最新价']
                    pct_change = row.iloc[0]['涨跌幅']
                    return {'price': price, 'pct_change': pct_change}
            
            elif market == 'hk':
                # yfinance works for HK too usually (e.g. 0700.HK)
                hk_symbol = f"{int(symbol):04d}.HK" # Format 00700 -> 0700.HK
                ticker = yf.Ticker(hk_symbol)
                price = ticker.fast_info.last_price
                prev_close = ticker.fast_info.previous_close
                if price and prev_close:
                     pct_change = ((price - prev_close) / prev_close) * 100
                     return {'price': price, 'pct_change': pct_change}

        except Exception as e:
            logger.error(f"Error fetching data for {symbol} ({market}): {e}")
            return None
        return None

    def check_significant_movement(self, watchlist, threshold=3.0):
        """
        Check for price movements > threshold%
        """
        alerts = []
        for region, stocks in watchlist.items():
            if region == 'keywords': continue
            
            for stock in stocks:
                symbol = stock['symbol']
                data = self.get_price_snapshot(symbol, market=region)
                if data:
                    pct = data['pct_change']
                    if abs(pct) >= threshold:
                        alerts.append({
                            'title': f"Stock Alert: {stock['name']} ({symbol})",
                            'content': f"Moved {pct:.2f}% (Current: {data['price']})",
                            'score': 8, # Auto high score for big movement
                            'type': 'market_movement'
                        })
        return alerts
