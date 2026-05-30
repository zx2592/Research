"""
Network date helpers with resilient fallbacks.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def _log(logger, level: str, message: str, *args) -> None:
    if logger is None:
        return
    log_fn = getattr(logger, level, None) or getattr(logger, "warning", None)
    if callable(log_fn):
        log_fn(message, *args)


def _request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AlphaSystem/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_headers(url: str):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AlphaSystem/1.0"},
        method="HEAD",
    )
    return urllib.request.urlopen(request, timeout=5)


def get_network_date(logger=None) -> tuple[str, str]:
    """
    Return a best-effort network-backed date as (YYYYMMDD, YYYY-MM-DD).
    Falls back to the local system clock only after all remote sources fail.
    """
    try:
        with _request_headers("https://www.baidu.com") as response:
            http_date = response.headers.get("Date")
        if http_date:
            dt = parsedate_to_datetime(http_date)
            return dt.strftime("%Y%m%d"), dt.strftime("%Y-%m-%d")
    except Exception as exc:
        _log(logger, "debug", "Baidu HTTP Date 获取失败: %s", exc)

    try:
        with _request_headers("https://www.taobao.com") as response:
            http_date = response.headers.get("Date")
        if http_date:
            dt = parsedate_to_datetime(http_date)
            return dt.strftime("%Y%m%d"), dt.strftime("%Y-%m-%d")
    except Exception as exc:
        _log(logger, "debug", "Taobao HTTP Date 获取失败: %s", exc)

    try:
        data = _request_json("https://worldtimeapi.org/api/timezone/Etc/UTC")
        dt = datetime.fromisoformat(data["datetime"])
        return dt.strftime("%Y%m%d"), dt.strftime("%Y-%m-%d")
    except Exception as exc:
        _log(logger, "warning", "worldtimeapi 获取失败: %s", exc)

    try:
        data = _request_json("https://timeapi.io/api/Time/current/zone?timeZone=UTC")
        dt = datetime(
            data["year"],
            data["month"],
            data["day"],
            data.get("hour", 0),
            data.get("minute", 0),
            data.get("seconds", 0),
        )
        return dt.strftime("%Y%m%d"), dt.strftime("%Y-%m-%d")
    except Exception as exc:
        _log(logger, "warning", "timeapi.io 获取失败: %s", exc)

    try:
        import ntplib

        ntp = ntplib.NTPClient()
        response = ntp.request("ntp.aliyun.com", version=3)
        dt = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
        return dt.strftime("%Y%m%d"), dt.strftime("%Y-%m-%d")
    except Exception as exc:
        _log(logger, "warning", "ntplib 获取失败: %s", exc)

    _log(logger, "warning", "网络时间不可用，使用系统时钟")
    now = datetime.now()
    return now.strftime("%Y%m%d"), now.strftime("%Y-%m-%d")
