"""
Tests for core/network_time.py.
"""
from datetime import datetime, timezone
from email.utils import format_datetime
from types import ModuleType, SimpleNamespace

from core import network_time


class _FakeResponse:
    def __init__(self, payload=None, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeLogger:
    def __init__(self):
        self.messages = []

    def warning(self, message, *args):
        if args:
            message = message % args
        self.messages.append(message)

    def debug(self, message, *args):
        if args:
            message = message % args
        self.messages.append(message)


def test_get_network_date_prefers_worldtimeapi(monkeypatch):
    payload = b'{"datetime":"2026-04-07T12:34:56+00:00"}'

    def fake_urlopen(request, timeout=0):
        if getattr(request, "method", "GET") == "HEAD":
            return _FakeResponse(headers={})
        return _FakeResponse(payload=payload)

    monkeypatch.setattr(network_time.urllib.request, "urlopen", fake_urlopen)

    compact, iso = network_time.get_network_date()

    assert compact == "20260407"
    assert iso == "2026-04-07"


def test_get_network_date_falls_back_to_timeapi(monkeypatch):
    responses = [
        _FakeResponse(headers={}),
        _FakeResponse(headers={}),
        RuntimeError("worldtime down"),
        _FakeResponse(
            payload=(
                b'{"year":2026,"month":4,"day":8,'
                b'"hour":9,"minute":30,"seconds":1}'
            )
        ),
    ]

    def fake_urlopen(request, timeout=0):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(network_time.urllib.request, "urlopen", fake_urlopen)

    compact, iso = network_time.get_network_date()

    assert compact == "20260408"
    assert iso == "2026-04-08"


def test_get_network_date_uses_taobao_http_date_header_when_available(monkeypatch):
    http_date = format_datetime(
        datetime(2026, 4, 9, 15, 16, 17, tzinfo=timezone.utc),
        usegmt=True,
    )
    responses = [
        RuntimeError("baidu down"),
        _FakeResponse(headers={"Date": http_date}),
    ]

    def fake_urlopen(request, timeout=0):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(network_time.urllib.request, "urlopen", fake_urlopen)

    compact, iso = network_time.get_network_date()

    assert compact == "20260409"
    assert iso == "2026-04-09"


def test_get_network_date_uses_ntplib_when_available(monkeypatch):
    logger = _FakeLogger()

    def fake_urlopen(request, timeout=0):
        raise RuntimeError("https unavailable")

    fake_ntplib = ModuleType("ntplib")

    class _FakeNTPClient:
        def request(self, host, version=3):
            assert host == "ntp.aliyun.com"
            assert version == 3
            return SimpleNamespace(tx_time=1775510400)

    fake_ntplib.NTPClient = _FakeNTPClient

    import sys

    monkeypatch.setattr(network_time.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setitem(sys.modules, "ntplib", fake_ntplib)

    compact, iso = network_time.get_network_date(logger=logger)

    assert compact == "20260406"
    assert iso == "2026-04-06"
    assert any("worldtimeapi" in message for message in logger.messages)
    assert any("timeapi.io" in message for message in logger.messages)


def test_get_network_date_falls_back_to_local_clock(monkeypatch):
    logger = _FakeLogger()

    def fake_urlopen(request, timeout=0):
        raise RuntimeError("all providers unavailable")

    class _FixedDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 4, 10, 8, 0, 0)

        @classmethod
        def fromtimestamp(cls, ts, tz=None):
            return datetime.fromtimestamp(ts, tz=tz)

    monkeypatch.setattr(network_time.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(network_time, "datetime", _FixedDateTime)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "ntplib":
            raise ImportError("No module named 'ntplib'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    compact, iso = network_time.get_network_date(logger=logger)

    assert compact == "20260410"
    assert iso == "2026-04-10"
    assert any("ntplib" in message for message in logger.messages)
    assert any("使用系统时钟" in message for message in logger.messages)
