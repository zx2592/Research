#!/usr/bin/env python3
"""
Data Manager - Unified Data Fetching Manager
v2.0

Integrates all information fetching channels:
1. RSS Free Subscription
2. yfinance Real-time Prices
3. tushare A-share Data
4. Tavily Web Search
5. Brave Search Fallback
"""

import os
import sys
import json
import logging
from datetime import datetime

from core import config  # noqa: F401 — ensures load_dotenv runs once
from core import settings

logger = logging.getLogger(__name__)

# Project Root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DataManager:
    """Unified Data Manager"""

    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
        self.tushare_token = os.getenv("TUSHARE_TOKEN")
        self._search_count = 0
        self.max_searches = settings.search.max_searches

    # ========== RSS ==========

    def fetch_rss(self, days=1, output_path=None):
        """Fetch market insights from RSS sources"""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
        try:
            from fetch_rss import fetch_all_sources
            result = fetch_all_sources(days)

            if result and result.get("count", 0) > 0 and output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                logger.info("RSS 数据已保存: %s", output_path)

            return result
        except Exception as e:
            logger.warning("RSS 获取失败: %s", e)
            return None
        finally:
            sys.path.pop(0)

    # ========== yfinance 价格数据 ==========

    def fetch_market_prices(self, tickers=None):
        """
        使用 yfinance 获取实时价格数据
        Returns: list of dict with ticker, name, change, price, type
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed")
            return []

        if tickers is None:
            tickers = load_holdings(PROJECT_ROOT)

        # Load skip list for tickers yfinance cannot price (futures etc.)
        _skip_price = set()
        try:
            _hp = os.path.join(PROJECT_ROOT, "Config", "holdings.json")
            with open(_hp, "r", encoding="utf-8") as _f:
                _hdata = json.load(_f)
            _skip_price = set(_hdata.get("no_price_tickers", []))
        except Exception as e:
            logger.warning("Failed to load no_price_tickers: %s", e)

        results = []
        # Use faster urllib-based fetch if possible to avoid WAF issues
        from services.datahub.sources.yfinance_src import _fetch_quote_via_urllib

        results = []
        for ticker, meta in tickers.items():
            info = {"ticker": ticker, "name": meta.get("name", ticker),
                    "change": 0.0, "type": meta.get("type", "stock"),
                    "logic": meta.get("logic", "-"), "risk": meta.get("risk", "-")}
            
            if ticker in _skip_price:
                results.append(info)
                continue
                
            try:
                # Normalize ticker for Yahoo Finance
                t_fixed = ticker
                if ticker.endswith(".SH"):
                    t_fixed = ticker.replace(".SH", ".SS")
                elif ticker.endswith(".HK"):
                    code = ticker.split('.')[0]
                    t_fixed = f"{code.lstrip('0').zfill(4)}.HK"

                # Attempt direct API fetch (Fast & Reliable)
                quote = _fetch_quote_via_urllib(t_fixed)
                price = quote.get("price")
                previous_close = quote.get("previous_close")

                if price is not None:
                    info['price'] = price
                    if previous_close not in (None, 0):
                        info['change'] = ((price - previous_close) / previous_close) * 100
                    else:
                        info['change'] = 0.0
                else:
                    # Fallback to yfinance library if direct fetch fails
                    import yfinance as yf
                    t_obj = yf.Ticker(t_fixed)
                    hist = t_obj.history(period="2d")
                    if not hist.empty:
                        info['price'] = hist['Close'].iloc[-1]
                        if len(hist) >= 2:
                            change_pct = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                            info['change'] = change_pct
            except Exception as e:
                logger.warning("Market fetch failed for %s: %s", ticker, e)
                info["price_error"] = str(e)

            results.append(info)

        return results


    # ========== tushare A股 ==========

    def fetch_cn_market(self, trade_date=None):
        """获取 A 股涨跌幅数据"""
        if not self.tushare_token:
            logger.warning("TUSHARE_TOKEN not configured")
            return {"top_gainers": [], "top_losers": []}

        try:
            import tushare as ts
            ts.set_token(self.tushare_token)
            pro = ts.pro_api()

            if not trade_date:
                trade_date = datetime.now().strftime("%Y%m%d")

            df = pro.daily(trade_date=trade_date, fields='ts_code,name,pct_chg')
            if df is not None and not df.empty:
                top_gainers = df.nlargest(5, 'pct_chg').to_dict('records')
                top_losers = df.nsmallest(5, 'pct_chg').to_dict('records')
                return {"top_gainers": top_gainers, "top_losers": top_losers}
        except Exception as e:
            logger.warning("tushare 获取失败: %s", e)

        return {"top_gainers": [], "top_losers": []}

    # ========== Tavily 搜索 ==========

    def search_web(self, query, max_results=5, depth="advanced"):
        """Tavily 网络搜索"""
        self._search_count += 1

        if self._search_count > self.max_searches:
            return f"[搜索配额已用完: 本次已搜索 {self.max_searches} 次]"

        # Quota warning
        warn_threshold = int(self.max_searches * settings.search.quota_warn_pct / 100)
        if self._search_count == warn_threshold:
            logger.warning("搜索配额预警: 已使用 %d/%d (%d%%)",
                           self._search_count, self.max_searches, settings.search.quota_warn_pct)

        logger.info("[%d/%d] 搜索: %s", self._search_count, self.max_searches, query)

        if not self.tavily_key:
            return "[Error: TAVILY_API_KEY not configured]"

        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=self.tavily_key)
            response = tavily.search(query=query, search_depth=depth, max_results=max_results)

            context = []
            for result in response.get("results", []):
                context.append(
                    f"标题: {result.get('title', '')}\n"
                    f"来源: {result.get('url', '')}\n"
                    f"内容: {result.get('content', '')[:settings.search.content_truncation]}\n---"
                )
            return "\n".join(context) if context else "[未找到相关结果]"
        except Exception as e:
            return f"[搜索错误: {e}]"

    def reset_search_counter(self):
        """重置搜索计数器"""
        self._search_count = 0

    # ========== Brave 搜索 ==========

    def search_brave(self, query, max_results=5):
        """Brave Search 备用搜索"""
        if not self.brave_key:
            return "[Error: BRAVE_SEARCH_API_KEY not configured]"

        try:
            import requests
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.brave_key
            }
            params = {"q": query, "count": max_results}
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers, params=params, timeout=10
            )

            if response.ok:
                data = response.json()
                results = []
                for item in data.get("web", {}).get("results", []):
                    results.append(
                        f"标题: {item.get('title', '')}\n"
                        f"来源: {item.get('url', '')}\n"
                        f"内容: {item.get('description', '')}\n---"
                    )
                return "\n".join(results) if results else "[未找到结果]"
            else:
                return f"[Brave Search Error: HTTP {response.status_code}]"
        except Exception as e:
            return f"[Brave Search Error: {e}]"

    # ========== 聚合获取 ==========

    def fetch_all(self, days=1, save=True):
        """一键获取所有渠道数据"""
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        month_str = now.strftime("%Y-%m")

        result = {
            "timestamp": now.isoformat(),
            "rss_data": None,
            "market_prices": [],
            "cn_market": {"top_gainers": [], "top_losers": []},
        }

        # 1. RSS
        rss_output = None
        if save:
            rss_output = os.path.join(
                PROJECT_ROOT, "Reports", "Raw_Data", month_str,
                f"financial_data_{date_str}.json"
            )
        result["rss_data"] = self.fetch_rss(days=days, output_path=rss_output)

        # 2. Market Prices
        result["market_prices"] = self.fetch_market_prices()

        # 3. CN Market
        result["cn_market"] = self.fetch_cn_market()

        return result


# ========== 动态持仓加载（单一真相来源）==========

def load_holdings(project_root: str = None) -> dict:
    """
    从 Config/holdings.json 读取实际持仓，返回与 fetch_market_prices 兼容的格式。
    若 JSON 不存在或读取失败，返回空字典并打印警告。
    """
    if project_root is None:
        project_root = PROJECT_ROOT
    holdings_path = os.path.join(project_root, "Config", "holdings.json")
    if not os.path.exists(holdings_path):
        logger.warning("Config/holdings.json 不存在。请先运行 parse_positions.py 生成持仓数据。")
        return {}
    try:
        with open(holdings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tickers = {}
        for sym, info in data.get("tickers", {}).items():
            tickers[sym] = {
                "name":     sym,
                "type":     "stock",
                "logic":    info.get("strategy", "-"),
                "risk":     "High" if info.get("strategy") == "Short-Term Satellite" else "Low",
                "sector":   info.get("sector", "Other"),
                "strategy": info.get("strategy", "-"),
            }
        return tickers
    except Exception as e:
        logger.warning("读取 holdings.json 失败: %s", e)
        return {}


# Sector ETFs（保留供其他模块使用）
SECTOR_ETFS = {
    "CN": [("512880.SH", "证券ETF"), ("512690.SH", "酒ETF"), ("512480.SH", "半导体"), ("159928.SZ", "消费ETF")],
    "US": [("XLK", "Tech"), ("XLF", "Finance"), ("XLE", "Energy"), ("XLV", "Health"), ("XLI", "Industrial")],
    "JP": [("1321.T", "Nikkei225"), ("1357.T", "TOPIX")],
}
