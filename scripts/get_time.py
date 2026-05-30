"""
获取网络校准时间 + 四市场状态矩阵
用法: python scripts/get_time.py
输出: JSON 格式的当前时间和市场状态，供 workflow 直接消费
"""

import json
import sys
from datetime import datetime, timezone, timedelta

UTC8 = timezone(timedelta(hours=8))


def get_network_time():
    """从网络获取准确的 UTC 时间，失败则 fallback 到本机"""

    # 方法1: worldtimeapi.org (免费, 无需 key)
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
            headers={"User-Agent": "AlphaSystem/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            # datetime 字符串格式: "2026-03-13T11:00:00.123456+08:00"
            dt_str = data["datetime"]
            # 截断到秒
            dt = datetime.fromisoformat(dt_str)
            return dt.astimezone(UTC8), "worldtimeapi"
    except Exception:
        pass

    # 方法2: timeapi.io
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://timeapi.io/api/time/current/zone?timeZone=Asia/Shanghai",
            headers={"User-Agent": "AlphaSystem/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            dt = datetime(
                data["year"], data["month"], data["day"],
                data["hour"], data["minute"], data["seconds"],
                tzinfo=UTC8
            )
            return dt, "timeapi.io"
    except Exception:
        pass

    # 方法3: NTP (需要 socket, 无第三方依赖)
    try:
        import socket
        import struct
        NTP_SERVER = "pool.ntp.org"
        NTP_PORT = 123
        NTP_EPOCH = 2208988800  # 1900-01-01 到 1970-01-01 的秒数

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(3)
        # NTP request packet
        data = b'\x1b' + 47 * b'\0'
        client.sendto(data, (NTP_SERVER, NTP_PORT))
        msg, _ = client.recvfrom(1024)
        client.close()

        # 解析返回的时间戳 (transmit timestamp at byte 40)
        t = struct.unpack("!12I", msg)[10] - NTP_EPOCH
        dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(UTC8)
        return dt, "ntp"
    except Exception:
        pass

    # Fallback: 本机时间 (不可靠, 标记警告)
    dt = datetime.now(UTC8)
    return dt, "local_clock (WARNING: may be inaccurate)"


def get_market_status(now_utc8):
    """根据 UTC+8 时间判断四市场状态"""
    h, m = now_utc8.hour, now_utc8.minute
    t = h * 60 + m  # 转为分钟方便比较
    weekday = now_utc8.weekday()  # 0=Monday, 6=Sunday

    def status(is_trading, close_time_minutes):
        """返回状态和收盘后经过的时间"""
        if is_trading:
            return "LIVE", "盘中"
        elapsed = t - close_time_minutes
        if elapsed < 0:
            elapsed += 24 * 60
        if elapsed <= 240:  # 4小时
            hours = elapsed // 60
            mins = elapsed % 60
            return "HOT", f"收盘{hours}h{mins}m"
        return "DARK", "隔夜休市"

    results = {}

    # 日股: 08:00-10:30, 11:30-14:00 (午休 10:30-11:30)
    jp_trading = (480 <= t < 630) or (690 <= t < 840)
    jp_close = 840  # 14:00
    if weekday >= 5:
        results["日股"] = ("HOLIDAY", "周末休市")
    else:
        s, desc = status(jp_trading, jp_close)
        # 午休期间也算 LIVE
        if 630 <= t < 690 and weekday < 5:
            s, desc = "LIVE", "午休"
        results["日股"] = (s, desc)

    # A股: 09:30-11:30, 13:00-15:00 (午休 11:30-13:00)
    a_trading = (570 <= t < 690) or (780 <= t < 900)
    a_close = 900  # 15:00
    if weekday >= 5:
        results["A股"] = ("HOLIDAY", "周末休市")
    else:
        s, desc = status(a_trading, a_close)
        if 690 <= t < 780 and weekday < 5:
            s, desc = "LIVE", "午休"
        results["A股"] = (s, desc)

    # 港股: 09:30-12:00, 13:00-16:00 (午休 12:00-13:00)
    hk_trading = (570 <= t < 720) or (780 <= t < 960)
    hk_close = 960  # 16:00
    if weekday >= 5:
        results["港股"] = ("HOLIDAY", "周末休市")
    else:
        s, desc = status(hk_trading, hk_close)
        if 720 <= t < 780 and weekday < 5:
            s, desc = "LIVE", "午休"
        results["港股"] = (s, desc)

    # 美股: 22:30-05:00(次日) — 跨日处理
    us_trading = (t >= 1350) or (t < 300)  # 22:30=1350, 05:00=300
    us_close = 300  # 05:00
    # 美股周末: 周六全天 + 周日22:30之前
    us_weekend = (weekday == 5) or (weekday == 6 and t < 1350)
    if us_weekend:
        results["美股"] = ("HOLIDAY", "周末休市")
    else:
        s, desc = status(us_trading, us_close)
        results["美股"] = (s, desc)

    return results


def determine_focus(markets):
    """确定焦点市场"""
    priority = ["美股", "A股", "港股", "日股"]

    # 先找 LIVE
    for m in priority:
        if markets[m][0] == "LIVE":
            return m, "LIVE"

    # 再找 HOT
    for m in priority:
        if markets[m][0] == "HOT":
            return m, "HOT"

    # 全 DARK: 找下一个即将开盘的
    return priority[0], "DARK (前瞻)"


def main():
    now, source = get_network_time()

    markets = get_market_status(now)
    focus_market, focus_reason = determine_focus(markets)

    output = {
        "timestamp_utc8": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "date_compact": now.strftime("%Y%m%d"),
        "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
        "time_source": source,
        "markets": {
            name: {"status": s, "detail": d}
            for name, (s, d) in markets.items()
        },
        "focus_market": focus_market,
        "focus_reason": focus_reason,
        "routing_summary": (
            f"市场路由 @ {now.strftime('%H:%M')} UTC+8 → "
            f"焦点: {focus_market} ({focus_reason}) | "
            + " ".join(f"{n}({s})" for n, (s, _) in markets.items())
        )
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
