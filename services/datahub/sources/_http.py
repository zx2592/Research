"""零依赖 HTTP 取数helper — urllib 直连，失败回退 curl --noproxy。

行情站点（腾讯、东方财富）对代理不友好：走公司代理常常拿到 403 或空包，
而它们本身不需要鉴权。这里先用 urllib 直连，再回退到 `curl --noproxy '*'`，
两条路都不带凭证、不写任何 token。
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def build_url(url: str, params: dict | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urllib.parse.urlencode(params)}"


def _decode(raw: bytes) -> str:
    """行情接口混用 UTF-8 与 GBK（腾讯返回 GBK）。"""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _via_urllib(url: str, timeout: int) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with opener.open(req, timeout=timeout) as resp:
        return _decode(resp.read())


def _via_curl(url: str, timeout: int) -> str:
    result = subprocess.run(
        ["curl", "-s", "--noproxy", "*", "-H", f"User-Agent: {_UA}", url],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"curl failed ({result.returncode}): {url}")
    return _decode(result.stdout)


def http_get(url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    """GET 文本；urllib 直连优先，失败回退 curl --noproxy。"""
    target = build_url(url, params)
    try:
        return _via_urllib(target, timeout)
    except Exception as exc:  # noqa: BLE001 - 任何失败都值得回退再试一次
        logger.debug("[http_get] urllib failed for %s: %s", target, exc)
        return _via_curl(target, timeout)


def http_get_json(url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    return json.loads(http_get(url, params, timeout))


def to_float(value):
    """行情接口用 '-' / '' 表示缺失，别把它们当 0。"""
    if value in (None, "", "-", "—"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
