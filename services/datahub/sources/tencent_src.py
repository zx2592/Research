"""腾讯行情 DataSource — A股 / 港股 / 美股实时快照，零依赖、免鉴权。

存在的意义是给 `cross_validate_price` 提供一个**跨族**的第二来源：
现有的 fetch_market_prices 与 yfinance 都走 Yahoo chart API（intl-vendor 族），
互相比对得到的 0.00% 偏差不是高可信度，是同一份数据比了两遍。
腾讯行情属于 cn-exchange-relay 族，与 Yahoo 是两条独立链路。

用法：
    hub.fetch(source_name="tencent", ticker="600519")      # A股
    hub.fetch(source_name="tencent", ticker="0700.HK")     # 港股
    hub.fetch(source_name="tencent", ticker="NVDA")        # 美股
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.datahub.base import DataSource, DataSourceResult
from services.datahub.sources._http import http_get, to_float

logger = logging.getLogger(__name__)

QUOTE_URL = "https://qt.gtimg.cn/q="

# A 股 ~ 分隔协议的字段位（港美股布局不同，只取通用字段）
_A_FIELDS = {
    "change_amt": 31,
    "change_pct": 32,
    "high": 33,
    "low": 34,
    "turnover_amt_wan": 37,
    "turnover_rate": 38,
    "pe_ttm": 39,
    "float_cap_yi": 44,
    "market_cap_yi": 45,
    "pb": 46,
}


def normalize_code(ticker: str) -> tuple[str, str]:
    """把 ticker 转成腾讯行情代码，返回 (腾讯代码, 市场)。

    600519 / 600519.SH -> sh600519 (cn)
    000001 / 000001.SZ -> sz000001 (cn)
    0700.HK / 00700    -> hk00700  (hk)
    NVDA               -> usNVDA   (us)
    """
    raw = (ticker or "").strip()
    if not raw:
        raise ValueError("ticker is required")

    upper = raw.upper()
    if upper.endswith(".HK"):
        code = upper[:-3].lstrip("0")
        return f"hk{code.zfill(5)}", "hk"

    body = upper.replace(".SH", "").replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
    if body.isdigit():
        if len(body) == 5:  # 港股裸代码
            return f"hk{body}", "hk"
        if body.startswith(("6", "9", "5")):
            return f"sh{body}", "cn"
        if body.startswith(("4", "8")):
            return f"bj{body}", "cn"
        return f"sz{body}", "cn"

    return f"us{body}", "us"


def parse_quote(raw: str) -> dict:
    """解析 `v_shXXXXXX="字段1~字段2~...";` 格式。"""
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        return {}
    fields = raw[start + 1:end].split("~")
    if len(fields) < 6:
        return {}
    return {"_fields": fields}


class TencentQuoteSource(DataSource):
    """腾讯行情（qt.gtimg.cn）快照，覆盖 A股 / 港股 / 美股。"""

    name = "tencent"
    family = "cn-exchange-relay"

    def fetch(self, ticker: str, **kwargs) -> DataSourceResult:
        query = (ticker or "").strip()
        try:
            code, market = normalize_code(query)
        except ValueError as exc:
            return DataSourceResult(self.name, {"error": str(exc)}, query)

        try:
            raw = http_get(f"{QUOTE_URL}{code}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[tencent_src] fetch failed for %s: %s", code, exc)
            return DataSourceResult(self.name, {"ticker": query, "price": None, "error": str(exc)}, query)

        parsed = parse_quote(raw)
        fields = parsed.get("_fields") or []
        if len(fields) < 6:
            return DataSourceResult(
                self.name,
                {"ticker": query, "price": None, "error": f"未解析到行情: {code}"},
                query,
            )

        price = to_float(fields[3])
        prev_close = to_float(fields[4])
        payload = {
            "ticker": query,
            "tencent_code": code,
            "market": market,
            "name": fields[1],
            "price": price,
            "previous_close": prev_close,
            "open": to_float(fields[5]),
            "source_method": "qt.gtimg.cn",
            "family": self.family,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        if price is not None and prev_close not in (None, 0):
            payload["change_pct"] = round((price - prev_close) / prev_close * 100, 6)

        # 港美股的 ~ 分隔布局与 A 股不同，宁可不给也不要给错位的数字
        if market == "cn" and len(fields) > 46:
            for key, idx in _A_FIELDS.items():
                value = to_float(fields[idx])
                # 交易所自报的涨跌幅优先，取不到才用 price/prev_close 现算的兜底
                if key == "change_pct" and value is None:
                    continue
                payload[key] = value
            cap_yi = payload.get("market_cap_yi")
            if cap_yi and price:
                # 推算总股本，供 verify_market_cap 做验算；标明是推算而非披露值
                payload["implied_shares"] = round(cap_yi * 1e8 / price, 2)

        return DataSourceResult(self.name, payload, query)

    def doctor(self) -> DataSourceResult:
        """连通性自检：拿一次上证指数。"""
        try:
            raw = http_get(f"{QUOTE_URL}sh000001")
            ok = bool(parse_quote(raw).get("_fields"))
            return DataSourceResult(self.name, {"ok": ok, "endpoint": QUOTE_URL}, "doctor")
        except Exception as exc:  # noqa: BLE001
            return DataSourceResult(self.name, {"ok": False, "error": str(exc)}, "doctor")
