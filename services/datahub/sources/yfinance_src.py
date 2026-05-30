"""
yfinance DataSource Adapter

Wraps yfinance + Yahoo Finance WAF bypass (from KI: yahoo-finance-waf-bypass).
Uses urllib direct API call as primary, yfinance as fallback.
"""
import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)

_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _coerce_optional_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _fetch_quote_via_urllib(ticker: str) -> dict[str, Optional[float]]:
    """Return the latest price plus previous-close context from Yahoo chart API."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range=1d"
    )
    try:
        req = urllib.request.Request(url, headers=_YAHOO_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        result = data["chart"]["result"][0]
        meta = result.get("meta", {})

        price = meta.get("regularMarketPrice")
        if price is None:
            quotes = result.get("indicators", {}).get("quote", [])
            closes = quotes[0].get("close", []) if quotes else []
            price = next((item for item in reversed(closes) if item is not None), None)
        if price is None:
            price = meta.get("previousClose") or meta.get("chartPreviousClose")

        previous_close = meta.get("chartPreviousClose")
        if previous_close is None:
            previous_close = meta.get("previousClose")

        return {
            "price": _coerce_optional_float(price),
            "previous_close": _coerce_optional_float(previous_close),
        }
    except Exception as exc:
        logger.warning("[yfinance_src] urllib fetch failed for %s: %s", ticker, exc)
        return {"price": None, "previous_close": None}


def _fetch_price_via_urllib(ticker: str) -> Optional[float]:
    """Direct Yahoo Finance chart API price helper."""
    return _fetch_quote_via_urllib(ticker)["price"]


class YFinanceSource(DataSource):
    """
    Fetch market data (price, volume, 52w range) from Yahoo Finance.
    Primarily via direct urllib; falls back to yfinance library.
    """

    name = "yfinance"

    def fetch(self, ticker: str, period: str = "1d", **kwargs) -> DataSourceResult:
        # 1. Try direct Yahoo API (WAF bypass)
        quote = _fetch_quote_via_urllib(ticker)
        price = quote["price"]
        if price is not None:
            payload = {
                "ticker": ticker,
                "price": price,
                "source_method": "urllib_direct",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            previous_close = quote["previous_close"]
            if previous_close not in (None, 0):
                payload["previous_close"] = previous_close
                payload["change_pct"] = round(((price - previous_close) / previous_close) * 100, 6)
            return DataSourceResult(
                source_name=self.name,
                data=payload,
                query=ticker,
            )

        # 2. Fallback: yfinance library
        try:
            import yfinance as yf

            hist = yf.download(ticker, period=period, auto_adjust=True, progress=False)
            if not hist.empty:
                close = float(hist["Close"].iloc[-1])
                return DataSourceResult(
                    source_name=self.name,
                    data={
                        "ticker": ticker,
                        "price": close,
                        "source_method": "yfinance_lib",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                    query=ticker,
                )
        except Exception as exc:
            logger.warning("[yfinance_src] yfinance fallback failed: %s", exc)

        return DataSourceResult(
            source_name=self.name,
            data={"ticker": ticker, "price": None, "error": "all sources failed"},
            query=ticker,
        )
