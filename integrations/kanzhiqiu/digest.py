"""Daily research digest: fetch, summarize, and output.

Architecture (two-step because kanzhiqiu.com APIs need HttpOnly session cookies):

  Step 1 — Browser fetch (via Claude MCP / bookmarklet):
    Calls kanzhiqiu.com APIs using browser session cookies,
    saves results to data/kanzhiqiu/.cache/<date>.json

  Step 2 — Python summarize:
    Reads the JSON cache, fetches morning report TXT content
    (BOS URLs have embedded auth, no cookies needed),
    builds structured context for LLM workflow consumption.
"""

import json
import logging
import requests
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths relative to research/ directory
_RESEARCH_ROOT = Path(__file__).resolve().parent.parent.parent
DIGEST_DIR = _RESEARCH_ROOT / "data" / "kanzhiqiu"
CACHE_DIR = DIGEST_DIR / ".cache"


# ─── Step 1: Browser-side data fetching ────────────────────────────────────

BROWSER_FETCH_SCRIPT = r"""
(async () => {
  const today = new Date().toLocaleDateString('sv-SE');

  // 1. Morning reports (just metadata + TXT URLs; content fetched by Python)
  const mrResp = await fetch('/newreport/findMorningReports.json', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'pageNo=1&pageSize=5', credentials: 'include'
  });
  const mrData = await mrResp.json();
  const morningReports = (mrData.data?.reports || [])
    .filter(r => new Date(r.DOCTIME).toLocaleDateString('sv-SE') === today)
    .map(r => ({id: r.ID, title: r.TITLE, txtUrl: r.TXTURL || ''}));

  // 2. Hot topics
  const htResp = await fetch('/shared/qaList.json', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'pageNo=1&pageSize=50', credentials: 'include'
  });
  const htData = await htResp.json();
  const hotTopics = (htData.data?.list || [])
    .filter(t => t.sharingTime?.startsWith(today))
    .map(t => ({
      question: t.question, time: t.sharingTime,
      entities: (t.entityList || []).map(e => e.entity)
    }));

  // 3. Viewpoint summaries
  const vpResp = await fetch('/shared/viewpointNews.json', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'pageNo=1&pageSize=10', credentials: 'include'
  });
  const vpData = await vpResp.json();
  const viewpoints = (vpData.data?.list || [])
    .filter(v => v.sharingTime?.startsWith(today))
    .map(v => ({
      question: v.question, time: v.sharingTime,
      entities: (v.entityList || []).map(e => e.entity)
    }));

  // 4. News focus
  const nfResp = await fetch('/newsadapter2/cjnews/newsFocus.json', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'pageNo=1&pageSize=30', credentials: 'include'
  });
  const nfData = await nfResp.json();
  const news = (nfData.data || []).slice(0, 30).map(r => ({
    title: (r.title || '').replace(/<[^>]+>/g, ''),
    broker: r.brokerName || '', docType: r.docTypeName || '',
    stock: r.STKNAME || '', rank: r.investrank || ''
  }));

  return JSON.stringify({
    date: today, fetchedAt: new Date().toISOString(),
    morningReports, hotTopics, viewpoints, news
  });
})()
""".strip()


def save_browser_data(json_str: str) -> Path:
    """Save browser-fetched JSON data to cache."""
    data = json.loads(json_str)
    date_str = data["date"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{date_str}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ─── Step 2: Python-side processing ───────────────────────────────────────

def load_cached_data(target_date: date | None = None) -> dict | None:
    """Load browser-fetched data from cache."""
    date_str = (target_date or date.today()).strftime("%Y-%m-%d")
    path = CACHE_DIR / f"{date_str}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_morning_content(txt_url: str) -> str:
    """Fetch morning report TXT content from BOS (no cookies needed)."""
    if not txt_url:
        return ""
    try:
        from urllib.parse import unquote
        url = unquote(txt_url)
        resp = requests.get(url, timeout=15)
        resp.encoding = "utf-8"
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch morning report TXT: {e}")
    return ""


def build_context(data: dict) -> str:
    """Build structured text context from cached data for LLM consumption."""
    parts = [f"# 研报数据 — {data['date']}\n"]

    # Morning report content
    if data.get("morningReports"):
        parts.append("## 一、晨会纪要\n")
        for r in data["morningReports"]:
            parts.append(f"### {r['title']}\n")
            content = r.get("content", "")
            if content:
                parts.append(content[:8000])
            parts.append("")

    # Viewpoint summaries
    if data.get("viewpoints"):
        parts.append("## 二、晨报汇总\n")
        for v in data["viewpoints"]:
            entities_str = ", ".join(v.get("entities", [])[:10])
            parts.append(f"- **{v['question']}**")
            if entities_str:
                parts.append(f"  涉及: {entities_str}")
        parts.append("")

    # Hot topics
    if data.get("hotTopics"):
        parts.append("## 三、热点话题\n")
        for t in data["hotTopics"]:
            entities_str = ", ".join(t.get("entities", [])[:8])
            parts.append(f"- {t['question']}")
            if entities_str:
                parts.append(f"  涉及: {entities_str}")
        parts.append("")

    # News focus
    if data.get("news"):
        parts.append("## 四、综合推荐\n")
        for item in data["news"][:20]:
            line = f"- [{item.get('docType', '')}] {item['title']}"
            if item.get("broker"):
                line += f" ({item['broker']})"
            if item.get("stock"):
                line += f" | {item['stock']}"
            if item.get("rank"):
                line += f" | 评级: {item['rank']}"
            parts.append(line)
        parts.append("")

    return "\n".join(parts)


def enrich_morning_content(data: dict) -> dict:
    """Fetch morning report TXT content for all reports in data (mutates in-place)."""
    for r in data.get("morningReports", []):
        if r.get("txtUrl") and not r.get("content"):
            logger.info(f"  Fetching morning report: {r['title'][:40]}...")
            r["content"] = fetch_morning_content(r["txtUrl"])
    return data


def get_today_digest() -> str:
    """Main entry: load cached data, enrich morning content, return context string.

    Returns empty string if no data available.
    """
    data = load_cached_data()
    if not data:
        return ""

    enrich_morning_content(data)

    total = (len(data.get("morningReports", []))
             + len(data.get("hotTopics", []))
             + len(data.get("viewpoints", []))
             + len(data.get("news", [])))
    if total == 0:
        return ""

    return build_context(data)
