"""腾讯 / 东方财富 数据源测试 — 代码归一化与响应解析（HTTP 全部打桩）。"""

import json
from unittest.mock import patch

import pytest

from services.datahub.sources.eastmoney_src import EastmoneySource, normalize_secid
from services.datahub.sources.tencent_src import (
    TencentQuoteSource,
    normalize_code,
    parse_quote,
)

def _tencent_a_payload(**overrides) -> str:
    """按字段位构造腾讯 A 股 ~ 分隔报文，避免手数分隔符数错位。"""
    fields = [str(i) for i in range(50)]
    layout = {
        1: "贵州茅台", 2: "600519", 3: "1500.00", 4: "1490.00", 5: "1495.00",
        6: "12345", 31: "10.00", 32: "0.67", 33: "1510.00", 34: "1480.00",
        37: "185000", 38: "0.35", 39: "30.5", 44: "2800.00", 45: "19000.00", 46: "9.8",
    }
    layout.update(overrides)
    for idx, value in layout.items():
        fields[idx] = value
    return 'v_sh600519="' + "~".join(fields) + '";'


_TENCENT_A = _tencent_a_payload()


class TestNormalizeCode:
    @pytest.mark.parametrize(
        "ticker,expected",
        [
            ("600519", ("sh600519", "cn")),
            ("600519.SH", ("sh600519", "cn")),
            ("600519.SS", ("sh600519", "cn")),
            ("000001", ("sz000001", "cn")),
            ("300750.SZ", ("sz300750", "cn")),
            ("430047", ("bj430047", "cn")),
            ("0700.HK", ("hk00700", "hk")),
            ("09992.HK", ("hk09992", "hk")),
            ("00700", ("hk00700", "hk")),
            ("NVDA", ("usNVDA", "us")),
        ],
    )
    def test_market_routing(self, ticker, expected):
        assert normalize_code(ticker) == expected

    def test_empty_ticker_raises(self):
        with pytest.raises(ValueError):
            normalize_code("  ")


class TestParseQuote:
    def test_parses_tilde_payload(self):
        fields = parse_quote(_TENCENT_A)["_fields"]
        assert fields[1] == "贵州茅台"
        assert fields[3] == "1500.00"

    def test_garbage_returns_empty(self):
        assert parse_quote("not a quote") == {}


class TestTencentQuoteSource:
    def test_a_share_quote_includes_valuation_fields(self):
        with patch("services.datahub.sources.tencent_src.http_get", return_value=_TENCENT_A):
            data = TencentQuoteSource().fetch(ticker="600519").data

        assert data["name"] == "贵州茅台"
        assert data["price"] == 1500.0
        assert data["market"] == "cn"
        assert data["family"] == "cn-exchange-relay"
        # 交易所自报的涨跌幅优先于 price/prev_close 现算的兜底值
        assert data["change_pct"] == 0.67
        assert data["market_cap_yi"] == 19000.0
        assert data["pb"] == 9.8
        # 总股本是从市值/股价推算的，标明来源避免被当成披露值
        assert data["implied_shares"] == pytest.approx(19000 * 1e8 / 1500.0, rel=1e-6)

    def test_hk_quote_omits_a_share_only_fields(self):
        payload = 'v_hk00700="100~腾讯控股~00700~600.000~595.000~598.000~1000~500~500";'
        with patch("services.datahub.sources.tencent_src.http_get", return_value=payload):
            data = TencentQuoteSource().fetch(ticker="0700.HK").data

        assert data["price"] == 600.0
        assert data["market"] == "hk"
        assert data["change_pct"] == pytest.approx(0.8403, abs=1e-3)
        # 港股字段布局与 A 股不同，宁可不给也不要给错位的数字
        assert "market_cap_yi" not in data
        assert "pe_ttm" not in data

    def test_network_failure_returns_error_payload_not_exception(self):
        with patch("services.datahub.sources.tencent_src.http_get", side_effect=ConnectionError("boom")):
            data = TencentQuoteSource().fetch(ticker="600519").data

        assert data["price"] is None
        assert "boom" in data["error"]

    def test_unparseable_payload_is_reported(self):
        with patch("services.datahub.sources.tencent_src.http_get", return_value='v_sh600519="";'):
            data = TencentQuoteSource().fetch(ticker="600519").data
        assert data["price"] is None
        assert "未解析到行情" in data["error"]


class TestNormalizeSecid:
    @pytest.mark.parametrize(
        "ticker,expected",
        [
            ("600519", "1.600519"),
            ("600519.SH", "1.600519"),
            ("000001", "0.000001"),
            ("430047.BJ", "0.430047"),
            ("0700.HK", "116.00700"),
        ],
    )
    def test_secid_prefixes(self, ticker, expected):
        assert normalize_secid(ticker) == expected

    def test_us_ticker_rejected(self):
        with pytest.raises(ValueError):
            normalize_secid("NVDA")


class TestEastmoneySource:
    def test_quote_maps_fields_including_52w_range(self):
        payload = {
            "data": {
                "f43": 1500.0, "f58": "贵州茅台", "f60": 1490.0, "f116": 1.9e12,
                "f117": 1.9e12, "f162": 30.5, "f167": 9.8, "f170": 0.67,
                "f174": 1800.0, "f175": 1200.0,
            }
        }
        with patch("services.datahub.sources.eastmoney_src.http_get_json", return_value=payload):
            data = EastmoneySource().fetch(ticker="600519").data

        assert data["price"] == 1500.0
        assert data["high_52w"] == 1800.0
        assert data["low_52w"] == 1200.0
        assert data["family"] == "cn-exchange-relay"

    def test_quote_falls_back_to_second_host(self):
        calls = []

        def flaky(url, params=None, timeout=15):
            calls.append(url)
            if "push2delay" in url:
                raise ConnectionError("rate limited")
            return {"data": {"f43": 10.0, "f58": "平安银行"}}

        with patch("services.datahub.sources.eastmoney_src.http_get_json", side_effect=flaky):
            data = EastmoneySource().fetch(ticker="000001").data

        assert data["price"] == 10.0
        assert len(calls) == 2

    def test_financials_returns_annual_periods(self):
        payload = {"result": {"data": [
            {
                "REPORT_DATE": "2025-12-31 00:00:00", "REPORT_DATE_NAME": "2025年报",
                "TOTALOPERATEREVE": 1.7e11, "TOTALOPERATEREVETZ": 12.3,
                "PARENTNETPROFIT": 8.5e10, "PARENTNETPROFITTZ": 14.0,
                "EPSJB": 68.0, "BPS": 200.0, "ROEJQ": 34.0, "XSMLL": 91.5,
            }
        ]}}
        with patch("services.datahub.sources.eastmoney_src.http_get_json", return_value=payload):
            data = EastmoneySource().fetch(ticker="600519", kind="financials").data

        period = data["periods"][0]
        assert period["report_date"] == "2025-12-31"
        assert period["revenue"] == 1.7e11
        assert period["roe_weighted_pct"] == 34.0

    def test_financials_missing_data_is_reported_not_faked(self):
        with patch("services.datahub.sources.eastmoney_src.http_get_json", return_value={"result": {}}):
            data = EastmoneySource().fetch(ticker="600519", kind="financials").data

        assert data["periods"] == []
        assert "证据缺口" in data["error"]

    def test_financials_rejects_non_a_share(self):
        data = EastmoneySource().fetch(ticker="NVDA", kind="financials").data
        assert "error" in data
        assert data["periods"] == [] if "periods" in data else True

    def test_result_is_json_serialisable(self):
        payload = {"data": {"f43": 10.0, "f58": "平安银行"}}
        with patch("services.datahub.sources.eastmoney_src.http_get_json", return_value=payload):
            result = EastmoneySource().fetch(ticker="000001")
        json.dumps(result.to_dict())
