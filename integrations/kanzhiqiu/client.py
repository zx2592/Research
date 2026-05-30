"""HTTP client for kanzhiqiu.com APIs.

All APIs require authentication via JSESSIONID cookie (HttpOnly).
Cookies are loaded from Chrome's cookie database automatically.
"""

import json
import logging
import re
import requests
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kanzhiqiu.com"

# Cookie cache stored alongside other data caches
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
COOKIE_CACHE = _DATA_DIR / ".kanzhiqiu_cookies.json"


@dataclass
class MorningReport:
    """晨会纪要 (Morning Meeting Report)."""
    id: int
    title: str
    doc_time: date
    txt_url: str = ""
    mp3_url: str = ""
    srt_url: str = ""
    content: str = ""


@dataclass
class HotTopic:
    """热点话题 (Hot Topic / Research Question)."""
    id: int
    question: str
    key_id: str
    sharing_time: str
    source: int = 0
    entities: list[dict] = field(default_factory=list)


@dataclass
class NewsFocusItem:
    """综合推荐 快讯/研报 (News Feed Item)."""
    id: str
    title: str
    broker: str = ""
    author: str = ""
    doc_type: str = ""
    stock_name: str = ""
    stock_code: str = ""
    industry: str = ""
    invest_rank: str = ""
    create_at: str = ""
    text: str = ""


@dataclass
class ViewpointSummary:
    """每日晨报汇总 (Daily Viewpoint Summary)."""
    id: int
    log_id: int
    question: str
    key_id: str
    sharing_time: str
    entities: list[dict] = field(default_factory=list)


def load_chrome_cookies(domain: str = ".kanzhiqiu.com") -> dict[str, str]:
    """Load cookies for a domain from Chrome's cookie database.

    Reads from Chrome's Cookies SQLite DB on Windows.
    Returns a dict of {name: value}.
    """
    import sqlite3
    import shutil
    import tempfile
    import os

    # Chrome cookie DB paths (Windows)
    local_app = os.environ.get("LOCALAPPDATA", "")
    cookie_paths = [
        Path(local_app) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
        Path(local_app) / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
    ]

    db_path = None
    for p in cookie_paths:
        if p.exists():
            db_path = p
            break

    if not db_path:
        raise FileNotFoundError(
            "Chrome cookie database not found. "
            "Login at kanzhiqiu.com in Chrome first."
        )

    # Copy DB to temp (Chrome locks it)
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(db_path, tmp)
    except (PermissionError, OSError):
        try:
            with open(db_path, "rb") as src:
                data = src.read()
            with open(tmp, "wb") as dst:
                dst.write(data)
        except (PermissionError, OSError) as e:
            raise PermissionError(
                f"Cannot read Chrome cookies (file locked by Chrome): {e}"
            ) from e

    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT name, value, encrypted_value FROM cookies "
            "WHERE host_key LIKE ?",
            (f"%{domain}%",)
        ).fetchall()
        conn.close()

        cookies = {}
        for name, value, enc_value in rows:
            if value:
                cookies[name] = value
            elif enc_value:
                try:
                    decrypted = _decrypt_chrome_cookie(enc_value, local_app)
                    if decrypted:
                        cookies[name] = decrypted
                except Exception:
                    pass
        return cookies
    finally:
        os.unlink(tmp)


def _decrypt_chrome_cookie(encrypted_value: bytes, local_app: str) -> str | None:
    """Decrypt Chrome cookie using Windows DPAPI or AES-GCM."""
    if not encrypted_value:
        return None

    # Chrome v80+ uses AES-256-GCM with key from Local State
    if encrypted_value[:3] == b"v10" or encrypted_value[:3] == b"v20":
        try:
            import base64
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            local_state_path = Path(local_app) / "Google" / "Chrome" / "User Data" / "Local State"
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)

            encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            encrypted_key = encrypted_key[5:]  # Remove "DPAPI" prefix

            import ctypes
            import ctypes.wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", ctypes.wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char)),
                ]

            p = ctypes.create_string_buffer(encrypted_key)
            blob_in = DATA_BLOB(len(encrypted_key), p)
            blob_out = DATA_BLOB()

            if ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)
            ):
                key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)

                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:]
                aesgcm = AESGCM(key)
                decrypted = aesgcm.decrypt(nonce, ciphertext, None)
                return decrypted.decode("utf-8")
        except Exception:
            return None

    # Old-style DPAPI encryption
    try:
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        p = ctypes.create_string_buffer(encrypted_value)
        blob_in = DATA_BLOB(len(encrypted_value), p)
        blob_out = DATA_BLOB()

        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0,
            ctypes.byref(blob_out)
        ):
            result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return result.decode("utf-8")
    except Exception:
        return None

    return None


def save_cookies_cache(cookies: dict[str, str]):
    """Save cookies to a local cache file."""
    COOKIE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_CACHE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")


def load_cookies_cache() -> dict[str, str] | None:
    """Load cookies from local cache."""
    if COOKIE_CACHE.exists():
        try:
            return json.loads(COOKIE_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


class KanzhiqiuClient:
    """Client for kanzhiqiu.com research report APIs."""

    def __init__(self, cookies: dict[str, str] | None = None, timeout: int = 15):
        self.session = requests.Session()
        self.timeout = timeout
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/newweb/zqsite/",
        })

        if cookies:
            for name, value in cookies.items():
                self.session.cookies.set(name, value, domain=".kanzhiqiu.com")
        else:
            self._load_cookies()

    def _load_cookies(self):
        """Try loading cookies from cache, then from Chrome."""
        cached = load_cookies_cache()
        if cached:
            for name, value in cached.items():
                self.session.cookies.set(name, value, domain=".kanzhiqiu.com")
            if self._check_session():
                return

        try:
            chrome_cookies = load_chrome_cookies()
            if chrome_cookies:
                for name, value in chrome_cookies.items():
                    self.session.cookies.set(name, value, domain=".kanzhiqiu.com")
                if self._check_session():
                    save_cookies_cache(chrome_cookies)
                    return
        except Exception as e:
            logger.warning(f"Failed to load Chrome cookies: {e}")

        logger.warning("No valid session cookies. Login at kanzhiqiu.com in Chrome first.")

    def _check_session(self) -> bool:
        """Check if the current session is authenticated."""
        try:
            resp = self.session.post(
                f"{BASE_URL}/newreport/findMorningReports.json",
                data={"pageNo": 1, "pageSize": 1},
                timeout=self.timeout,
            )
            data = resp.json()
            return data.get("ret") == 1
        except Exception:
            return False

    # ─── Morning Reports (晨会纪要) ─────────────────────────────────────

    def get_morning_reports(self, page: int = 1, page_size: int = 5) -> list[MorningReport]:
        """Fetch list of morning meeting reports."""
        resp = self.session.post(
            f"{BASE_URL}/newreport/findMorningReports.json",
            data={"pageNo": page, "pageSize": page_size},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        reports = []
        for r in data.get("data", {}).get("reports", []):
            reports.append(MorningReport(
                id=r["ID"],
                title=r["TITLE"],
                doc_time=datetime.fromtimestamp(r["DOCTIME"] / 1000).date(),
                txt_url=r.get("TXTURL", ""),
                mp3_url=r.get("MP3URL", ""),
                srt_url=r.get("SRTURL", ""),
            ))
        return reports

    def get_morning_report_content(self, report: MorningReport) -> str:
        """Fetch the text content of a morning report via its TXT URL."""
        if not report.txt_url:
            return ""
        try:
            resp = self.session.get(report.txt_url, timeout=self.timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            logger.warning(f"Failed to fetch TXT for {report.title}: {e}")
            return ""

    # ─── Hot Topics (热点话题) ──────────────────────────────────────────

    def get_hot_topics(self, page: int = 1, page_size: int = 30) -> list[HotTopic]:
        """Fetch today's hot research topics/questions."""
        resp = self.session.post(
            f"{BASE_URL}/shared/qaList.json",
            data={"pageNo": page, "pageSize": page_size},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        topics = []
        for item in data.get("data", {}).get("list", []):
            topics.append(HotTopic(
                id=item["id"],
                question=item["question"],
                key_id=item.get("keyId", ""),
                sharing_time=item.get("sharingTime", ""),
                source=item.get("source", 0),
                entities=item.get("entityList", []),
            ))
        return topics

    # ─── Daily Viewpoint Summary (每日晨报汇总) ────────────────────────

    def get_viewpoint_summaries(self, page_size: int = 10) -> list[ViewpointSummary]:
        """Fetch daily viewpoint/morning summaries."""
        resp = self.session.post(
            f"{BASE_URL}/shared/viewpointNews.json",
            data={"pageNo": 1, "pageSize": page_size},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        summaries = []
        for item in data.get("data", {}).get("list", []):
            summaries.append(ViewpointSummary(
                id=item["id"],
                log_id=item.get("logId", 0),
                question=item.get("question", ""),
                key_id=item.get("keyId", ""),
                sharing_time=item.get("sharingTime", ""),
                entities=item.get("entityList", []),
            ))
        return summaries

    # ─── News Focus (综合推荐) ─────────────────────────────────────────

    def get_news_focus(self, page: int = 1, page_size: int = 20) -> list[NewsFocusItem]:
        """Fetch recommended news/research feed."""
        resp = self.session.post(
            f"{BASE_URL}/newsadapter2/cjnews/newsFocus.json",
            data={"pageNo": page, "pageSize": page_size},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        items = []
        for r in data.get("data", []):
            items.append(NewsFocusItem(
                id=str(r.get("id", "")),
                title=_strip_html(r.get("title", "")),
                broker=r.get("brokerName", ""),
                author=r.get("author", ""),
                doc_type=r.get("docTypeName", ""),
                stock_name=r.get("STKNAME", ""),
                stock_code=r.get("STKCODE", ""),
                industry=r.get("industry", ""),
                invest_rank=r.get("investrank", ""),
                create_at=_ts_to_str(r.get("createat")),
                text=r.get("text", ""),
            ))
        return items


def _strip_html(text: str) -> str:
    """Remove simple HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text)


def _ts_to_str(ts) -> str:
    """Convert millisecond timestamp to datetime string."""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return ""
