"""
OpenBB DataSource Adapter

Wraps OpenBB Platform for multi-market fundamental + market data.
Supports equity, ETF, macro, and crypto data without API key
(community tier), or with API keys for premium sources.

Docs: https://docs.openbb.co/platform
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)


class OpenBBSource(DataSource):
    """
    Multi-market data via OpenBB Platform.

    Covers:
      - equity.price.historical (yfinance, polygon, etc.)
      - equity.fundamental.income (income statement)
      - equity.fundamental.ratios (P/E, ROE, etc.)
      - economy.calendar (macro events)

    Falls back gracefully when OpenBB is not installed.
    """
    name = "openbb"

    def __init__(self, provider: str = "yfinance"):
        """
        Args:
            provider: OpenBB provider backend (yfinance, polygon, fmp, etc.)
        """
        self.provider = provider

    def fetch(
        self,
        ticker: str,
        data_type: str = "price",
        period: str = "1y",
        **kwargs,
    ) -> DataSourceResult:
        """
        Fetch data from OpenBB.

        Args:
            ticker: Stock symbol (e.g. "NVDA", "AAPL")
            data_type: "price" | "income" | "ratios" | "calendar"
            period: Time period for historical data (e.g. "1y", "5y")
        """
        try:
            from openbb import obb
        except ImportError:
            logger.warning("[openbb_src] openbb-platform not installed. "
                           "Install: pip install openbb")
            return DataSourceResult(
                source_name=self.name,
                data={
                    "error": "openbb not installed",
                    "ticker": ticker,
                    "hint": "pip install openbb",
                },
                query=ticker,
            )

        try:
            if data_type == "price":
                result = obb.equity.price.historical(
                    ticker, provider=self.provider, **kwargs
                )
                df = result.to_df()
                latest = {}
                if not df.empty:
                    row = df.iloc[-1]
                    latest = {
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                        "date": str(df.index[-1]),
                    }
                return DataSourceResult(
                    source_name=self.name,
                    data={
                        "ticker": ticker,
                        "data_type": "price",
                        "latest": latest,
                        "provider": self.provider,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                    query=ticker,
                )

            elif data_type == "ratios":
                result = obb.equity.fundamental.ratios(
                    ticker, provider=self.provider, **kwargs
                )
                df = result.to_df()
                data = df.to_dict(orient="records") if not df.empty else []
                return DataSourceResult(
                    source_name=self.name,
                    data={
                        "ticker": ticker,
                        "data_type": "ratios",
                        "records": data[:5],  # latest 5 periods
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                    query=ticker,
                )

            elif data_type == "income":
                result = obb.equity.fundamental.income(
                    ticker, provider=self.provider, **kwargs
                )
                df = result.to_df()
                data = df.to_dict(orient="records") if not df.empty else []
                return DataSourceResult(
                    source_name=self.name,
                    data={
                        "ticker": ticker,
                        "data_type": "income",
                        "records": data[:4],  # latest 4 quarters/years
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                    query=ticker,
                )

            else:
                return DataSourceResult(
                    source_name=self.name,
                    data={
                        "error": f"Unknown data_type '{data_type}'",
                        "ticker": ticker,
                    },
                    query=ticker,
                )

        except Exception as e:
            logger.error(f"[openbb_src] Error fetching {ticker} ({data_type}): {e}")
            return DataSourceResult(
                source_name=self.name,
                data={"error": str(e), "ticker": ticker, "data_type": data_type},
                query=ticker,
            )
