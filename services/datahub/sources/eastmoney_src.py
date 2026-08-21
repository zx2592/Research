"""东方财富 DataSource — A股/港股行情 + A股年度核心财务，零依赖、免鉴权。

两个用途：
1. `kind="quote"`：补齐腾讯行情协议里没有的 **52 周高低**（f174/f175），
   以及市值 / PE / PB。
2. `kind="financials"`：拿**结构化年报数据**（营收、归母净利、EPS、ROE、增速）。
   深度与估值类研究最容易出错的地方，就是从新闻正文里读 OCF / 净利润 /ROIC——
   口径不明、常常还是别人算过一手的。能走结构化接口就不要走文本转述。

用法：
    hub.fetch(source_name="eastmoney", ticker="600519")                     # 行情
    hub.fetch(source_name="eastmoney", ticker="600519", kind="financials")  # 年报
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.datahub.base import DataSource, DataSourceResult
from services.datahub.sources._http import http_get_json, to_float

logger = logging.getLogger(__name__)

# push2 主站对连续请求限流较严；push2delay 的延时行情不影响 52 周极值与估值指标
QUOTE_HOSTS = ("push2delay.eastmoney.com", "push2.eastmoney.com")
FINANCE_URL = "https://datacenter.eastmoney.com/securities/api/data/get"

_QUOTE_FIELDS = "f43,f57,f58,f60,f116,f117,f162,f167,f170,f174,f175"


def normalize_secid(ticker: str) -> str:
    """ticker -> 东方财富 secid。沪市 1.，深/北 0.，港股 116.。"""
    raw = (ticker or "").strip().upper()
    if not raw:
        raise ValueError("ticker is required")
    if raw.endswith(".HK"):
        return f"116.{raw[:-3].lstrip('0').zfill(5)}"
    body = raw.replace(".SH", "").replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
    if not body.isdigit():
        raise ValueError(f"东方财富数据源只支持 A股/港股代码，收到: {ticker}")
    if len(body) == 5:
        return f"116.{body}"
    return f"1.{body}" if body.startswith(("6", "9", "5")) else f"0.{body}"


def _market_suffix(code: str) -> str:
    return "SH" if code.startswith(("6", "9", "5")) else "SZ"


class EastmoneySource(DataSource):
    """东方财富行情与年报财务。"""

    name = "eastmoney"
    family = "cn-exchange-relay"

    def fetch(self, ticker: str, kind: str = "quote", years: int = 5, **kwargs) -> DataSourceResult:
        if kind == "financials":
            return self._fetch_financials(ticker, years)
        return self._fetch_quote(ticker)

    # --- 行情 ---------------------------------------------------------------

    def _fetch_quote(self, ticker: str) -> DataSourceResult:
        query = (ticker or "").strip()
        try:
            secid = normalize_secid(query)
        except ValueError as exc:
            return DataSourceResult(self.name, {"error": str(exc)}, query)

        data = None
        last_error = "unknown"
        for host in QUOTE_HOSTS:
            try:
                payload = http_get_json(
                    f"https://{host}/api/qt/stock/get",
                    {"secid": secid, "fields": _QUOTE_FIELDS, "invt": "2", "fltt": "2"},
                )
                data = payload.get("data")
                if data:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

        if not data:
            return DataSourceResult(
                self.name,
                {"ticker": query, "price": None, "error": f"行情获取失败: {last_error}"},
                query,
            )

        price = to_float(data.get("f43"))
        prev_close = to_float(data.get("f60"))
        result = {
            "ticker": query,
            "secid": secid,
            "name": data.get("f58"),
            "price": price,
            "previous_close": prev_close,
            "change_pct": to_float(data.get("f170")),
            "market_cap": to_float(data.get("f116")),
            "float_cap": to_float(data.get("f117")),
            "pe_ttm": to_float(data.get("f162")),
            "pb": to_float(data.get("f167")),
            "high_52w": to_float(data.get("f174")),
            "low_52w": to_float(data.get("f175")),
            "source_method": "eastmoney.push2",
            "family": self.family,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if result["change_pct"] is None and price is not None and prev_close not in (None, 0):
            result["change_pct"] = round((price - prev_close) / prev_close * 100, 6)
        return DataSourceResult(self.name, result, query)

    # --- 财务 ---------------------------------------------------------------

    def _fetch_financials(self, ticker: str, years: int) -> DataSourceResult:
        query = (ticker or "").strip()
        code = query.upper().replace(".SH", "").replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
        if not code.isdigit() or len(code) != 6:
            return DataSourceResult(
                self.name,
                {"error": f"结构化年报目前只覆盖 A股 6 位代码，收到: {ticker}"},
                query,
            )

        secucode = f"{code}.{_market_suffix(code)}"
        base_params = {
            "type": "RPT_F10_FINANCE_MAINFINADATA",
            "sty": "ALL",
            "p": "1",
            "ps": str(max(1, years)),
            "sr": "-1",
            "st": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
        }

        reports = []
        # 先按年报筛；部分标的年报字段缺失时退回全部报告期
        for report_filter in (f'(SECUCODE="{secucode}")(REPORT_TYPE="年报")', f'(SECUCODE="{secucode}")'):
            try:
                params = dict(base_params, filter=report_filter)
                payload = http_get_json(FINANCE_URL, params)
                reports = (payload.get("result") or {}).get("data") or []
            except Exception as exc:  # noqa: BLE001
                logger.warning("[eastmoney_src] financials failed for %s: %s", secucode, exc)
                reports = []
            if reports:
                break

        if not reports:
            return DataSourceResult(
                self.name,
                {
                    "ticker": query,
                    "periods": [],
                    "error": "未取到结构化年报数据——如实记入证据缺口，不要用新闻正文里的数字替代",
                },
                query,
            )

        periods = []
        for row in reports[:years]:
            periods.append({
                "report_date": (row.get("REPORT_DATE") or "")[:10],
                "report_name": row.get("REPORT_DATE_NAME"),
                "revenue": to_float(row.get("TOTALOPERATEREVE")),
                "revenue_yoy_pct": to_float(row.get("TOTALOPERATEREVETZ")),
                "net_profit_attributable": to_float(row.get("PARENTNETPROFIT")),
                "net_profit_yoy_pct": to_float(row.get("PARENTNETPROFITTZ")),
                "eps": to_float(row.get("EPSJB")),
                "bps": to_float(row.get("BPS")),
                "roe_weighted_pct": to_float(row.get("ROEJQ")),
                "gross_margin_pct": to_float(row.get("XSMLL")),
                "operating_cashflow_ps": to_float(row.get("MGJYXJJE")),
            })

        return DataSourceResult(
            self.name,
            {
                "ticker": query,
                "secucode": secucode,
                "periods": periods,
                "source_method": "eastmoney.datacenter/RPT_F10_FINANCE_MAINFINADATA",
                "family": self.family,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
            query,
        )

    def doctor(self) -> DataSourceResult:
        try:
            payload = http_get_json(
                f"https://{QUOTE_HOSTS[0]}/api/qt/stock/get",
                {"secid": "1.000001", "fields": "f43,f58", "invt": "2", "fltt": "2"},
            )
            return DataSourceResult(self.name, {"ok": bool(payload.get("data")), "endpoint": QUOTE_HOSTS[0]}, "doctor")
        except Exception as exc:  # noqa: BLE001
            return DataSourceResult(self.name, {"ok": False, "error": str(exc)}, "doctor")
