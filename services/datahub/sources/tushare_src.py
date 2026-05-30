"""
Tushare DataSource Adapter

Wraps Tushare Pro API for A-share market data.
Requires TUSHARE_TOKEN in environment.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)


class TushareSource(DataSource):
    """A-share data via Tushare Pro API."""
    name = "tushare"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("TUSHARE_TOKEN", "")

    def _get_api(self):
        import tushare as ts
        ts.set_token(self.token)
        return ts.pro_api()

    def fetch(self, ticker: str, fields: str = "close,pct_chg,vol,amount", **kwargs) -> DataSourceResult:
        if not self.token:
            return DataSourceResult(
                source_name=self.name,
                data={"error": "TUSHARE_TOKEN not set"},
                query=ticker,
            )
        try:
            pro = self._get_api()
            today = datetime.now().strftime("%Y%m%d")
            df = pro.daily(ts_code=ticker, start_date=today, end_date=today, fields=fields)
            if df is not None and not df.empty:
                row = df.iloc[0].to_dict()
            else:
                row = {}
            return DataSourceResult(
                source_name=self.name,
                data={
                    "ticker": ticker,
                    "data": row,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
                query=ticker,
            )
        except Exception as e:
            logger.error(f"[tushare_src] Error: {e}")
            return DataSourceResult(
                source_name=self.name,
                data={"error": str(e), "ticker": ticker},
                query=ticker,
            )
