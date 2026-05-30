#!/usr/bin/env python3
"""
RSS Data Fetcher (Investment Scenario)

【This script is an implementation example for investment research】
- Data Sources: Investment Insight Blog RSS + Other Financial RSS
- Data Types: Free full-text market insights, industry dynamics, macro economics

【其他场景如何适配】
本脚本是三层架构「第一层：信息输入」的具体实现。
如果你是其他领域的知识工作者，可以参考本脚本的结构，替换为你的 RSS 源：
- 学术研究 → arXiv RSS / Nature/Science RSS
- 产品经理 → Product Hunt RSS / TechCrunch RSS
- 内容创作 → 微博热搜 RSS / 知乎热榜 RSS

核心不变：通过 RSS 自动抓取内容到本地，无需 API Key
核心可变：RSS_SOURCES 字典中的订阅源列表

【投资场景】免费数据源：
https://yongmai.xyz/category/daily-research/feed/
Yongmai 市场洞察日报，每日更新，全文输出。

如需更多投资类 RSS 源，可参考 Yongmai 博客的推荐清单。
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import argparse
import json
import ssl
import sys
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# 【Investment Scenario】Default RSS URL
# 【Other Scenarios】Modify to your main data source URL
DEFAULT_RSS_URL = "https://example.com/feed/"

# ============================================================
# 🔹 RSSHub 配置 (自建服务)
# ============================================================
RSSHUB_BASE = os.getenv("RSSHUB_BASE", "https://your-rsshub-domain.com")  # 从 .env 读取，避免硬编码上传

# ============================================================
# 🔹 数据源配置
# ============================================================
RSS_SOURCES = {
    # --- 默认启用 ---
    "市场洞察": DEFAULT_RSS_URL,

# ============================================================
# 🔹 SOP 1: 深度洞察 (Deep Dive)
# 战略价值：商业模式分析、科技趋势、深度宏观
# ============================================================
    # "The Information": "https://www.theinformation.com/feed",
    # "Stratechery": "https://stratechery.com/feed/",
     "Bloomberg Tech": "https://feeds.bloomberg.com/technology/news.rss",  # ✅ [Verified Working]
    # "Bloomberg Opinion (Matt Levine)": "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss",
     "FT Tech": "https://www.ft.com/technology?format=rss",  # ✅ [Verified Working]
    # "Seeking Alpha Editors Picks": "https://seekingalpha.com/tag/editors-picks.xml",
    # "The Economist": "https://www.economist.com/finance-and-economics/rss.xml",
     # "ARK Invest": "https://ark-invest.com/feed/",
     "东财·策略研报": f"{RSSHUB_BASE}/eastmoney/report/strategyreport",  # ✅ [Verified Working]
     "东财·宏观研究": f"{RSSHUB_BASE}/eastmoney/report/macresearch",

    # ============================================================
    # 🔹 SOP 2: 势能扫描 (Momentum Scan)
    # 战略价值：盘前/盘后动态、异动评级、资金流向
    # ============================================================
    # "MarketBeat Instant Alerts": "https://www.marketbeat.com/rss/instant-alerts.xml",
     "金十数据·重要": f"{RSSHUB_BASE}/jin10/:important?",  # ✅ [Verified Working]
     "金十·美股": f"{RSSHUB_BASE}/jin10/topic/424",
     "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss",  # ✅ [Verified Working]
     "FT Markets": "https://www.ft.com/markets?format=rss",  # ✅ [Verified Working]
     "财联社·热门": f"{RSSHUB_BASE}/cls/hot",  # ✅ [Verified Working]
    # "TechCrunch": "https://techcrunch.com/feed/",
    # "The Block": f"{RSSHUB_BASE}/theblock/category/crypto-ecosystems",
    # "Bloomberg Crypto": "https://feeds.bloomberg.com/crypto/news.rss",

    # ============================================================
    # 🔹 辅助：区域/垂类 (Auxiliary)
    # 战略价值：特定区域（东南亚/欧洲）、一级市场、技术博客
    # ============================================================
    # "TechInAsia": "https://www.techinasia.com/feed",
    # "Technode": "https://technode.com/feed/",
    # "EU-Startups": "https://www.eu-startups.com/feed/",
    # "AltAssets": "https://www.altassets.net/feed",
    # "东财·券商晨报": f"{RSSHUB_BASE}/eastmoney/report/brokerreport",
    # "MacroMicro": "https://sc.macromicro.me/feed",
    # "Followin": f"{RSSHUB_BASE}/followin/1/zh-Hans",
    # "Nvidia Blog": "https://blogs.nvidia.com/feed/",
    # "The Verge": "https://www.theverge.com/rss/index.xml",
}


def fetch_rss(url, days=1):
    """从 RSS 源获取数据"""
    print(f"🚀 正在获取 RSS 数据...")
    print(f"   数据源: {url}")
    print(f"   时间范围: 最近 {days} 天")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")

    # SSL Context
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            xml_content = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP 错误: {e.code} - {e.reason}")
        return None
    except urllib.error.URLError as e:
        print(f"❌ 网络错误: {e.reason}")
        return None
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        return None

    # 解析 RSS XML
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"❌ XML 解析错误: {e}")
        return None

    channel = root.find("channel")
    if channel is None:
        print("❌ 未找到 RSS channel")
        return None

    # 计算时间过滤阈值
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

    items = []
    for item in channel.findall("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        description = item.findtext("description", "").strip()

        # 尝试获取全文内容（content:encoded）
        content = ""
        for child in item:
            if "encoded" in child.tag:
                content = (child.text or "").strip()
                break

        # 解析发布时间
        parsed_date = None
        if pub_date:
            try:
                # RSS 标准时间格式: "Mon, 10 Feb 2026 02:00:00 +0000"
                parsed_date = datetime.strptime(
                    pub_date, "%a, %d %b %Y %H:%M:%S %z"
                )
            except ValueError:
                try:
                    parsed_date = datetime.strptime(
                        pub_date, "%a, %d %b %Y %H:%M:%S %Z"
                    )
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        # 时间过滤
        if parsed_date and parsed_date < cutoff_time:
            continue

        # 提取分类标签
        categories = [
            cat.text for cat in item.findall("category") if cat.text
        ]

        items.append({
            "title": title,
            "link": link,
            "pub_date": pub_date,
            "categories": categories,
            "description": description,
            "content": content if content else description,
        })

    result = {
        "source": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "time_range_days": days,
        "count": len(items),
        "data": items,
    }

    return result


def fetch_all_sources(days=1):
    """从所有配置的 RSS 源获取数据"""
    all_items = []

    for name, url in RSS_SOURCES.items():
        print(f"\n📡 [{name}]")
        result = fetch_rss(url, days)
        if result and result.get("data"):
            for item in result["data"]:
                item["source_name"] = name
            all_items.extend(result["data"])
            print(f"   ✅ 获取 {len(result['data'])} 条")
        else:
            print(f"   ⚠️ 未获取到数据")

    return {
        "sources": list(RSS_SOURCES.keys()),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "time_range_days": days,
        "count": len(all_items),
        "data": all_items,
    }


def main():
    parser = argparse.ArgumentParser(
        description="RSS Data Fetcher - Fetch market info from RSS sources"
    )
    parser.add_argument(
        "days",
        type=float,
        nargs="?",
        default=1,
        help="Fetch data for the last N days (Default: 1)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Specify single RSS URL (Uses all configured sources if not specified)",
    )
    parser.add_argument(
        "--output",
        default="financial_data.json",
        help="Output file path (Default: financial_data.json)",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("RSS Data Fetcher")
    print("=" * 50)

    if args.url:
        result = fetch_rss(args.url, args.days)
    else:
        result = fetch_all_sources(args.days)

    if result and result.get("count", 0) > 0:
        # Ensure output directory exists
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                print(f"📁 创建目录: {output_dir}")
            except OSError as e:
                print(f"❌ 创建目录失败: {e}")
                sys.exit(1)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 数据已保存: {args.output}")
        print(f"✅ 共获取 {result['count']} 条数据")

        # 分类统计
        if result.get("data"):
            cats = {}
            for item in result["data"]:
                for cat in item.get("categories", ["未分类"]):
                    cats[cat] = cats.get(cat, 0) + 1
            if cats:
                print("\n📁 分类统计:")
                for cat, num in sorted(cats.items()):
                    print(f"   {cat}: {num} 条")
    else:
        print("\n⚠️ 未获取到数据，请检查网络连接和 RSS 源地址")
        sys.exit(1)


if __name__ == "__main__":
    main()
