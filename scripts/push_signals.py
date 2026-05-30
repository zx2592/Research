#!/usr/bin/env python3
"""
Push stock signals to TradingSystem.

Reads holdings from Config/holdings.json, calculates annualized volatility
via yfinance, and writes YAML signal files to TradingSystem's signal folder.

Usage (via research_cli.py):
    python research_cli.py push all               # 推送全部持仓+观察列表
    python research_cli.py push NVDA              # 推送单个标的
    python research_cli.py push NVDA AAPL 0700.HK # 推送多个标的

Direct usage:
    python scripts/push_signals.py all
    python scripts/push_signals.py NVDA AAPL

Signal categories (auto-detected from holdings.json):
    - "Long-Term Core" / long_term_tickers → category: core
    - "Short-Term Satellite"               → category: noncore
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIGNAL_DIR = Path("D:/工作相关/自动化/TradingSystem/data/signals/alpha")
VOL_PERIOD = "1y"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Holdings ─────────────────────────────────────────────────────────────────

def load_holdings() -> dict:
    path = PROJECT_ROOT / "Config" / "holdings.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def classify_category(ticker: str, holdings: dict) -> str:
    long_term = set(holdings.get("long_term_tickers", []))
    strategy = holdings.get("tickers", {}).get(ticker, {}).get("strategy", "")
    if ticker in long_term or "Core" in strategy:
        return "core"
    return "noncore"


def get_all_tickers(holdings: dict) -> list[str]:
    """All held tickers + long_term watchlist, excluding cash."""
    held = set(holdings.get("tickers", {}).keys())
    long_term = set(holdings.get("long_term_tickers", []))
    cash = set(holdings.get("cash_tickers", []))
    return sorted((held | long_term) - cash)


# ── Volatility ───────────────────────────────────────────────────────────────

def calc_volatility(ticker: str) -> float | None:
    """Annualized volatility via yfinance. Returns e.g. 0.35 (=35%) or None."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        yf_ticker = ticker
        if ticker.endswith(".HK"):
            yf_ticker = f"{ticker.split('.')[0].lstrip('0')}.HK"

        data = yf.download(yf_ticker, period=VOL_PERIOD, progress=False,
                           auto_adjust=True, timeout=15)
        if data.empty or len(data) < 20:
            return None

        close = data["Close"].squeeze()
        vol = float(close.pct_change().dropna().std() * (252 ** 0.5))
        return round(vol, 4)
    except Exception:
        return None


# ── Signal building & writing ────────────────────────────────────────────────

def build_signal(ticker: str, holdings: dict, vol: float | None) -> dict:
    info = holdings.get("tickers", {}).get(ticker, {})
    category = classify_category(ticker, holdings)
    strategy = info.get("strategy", "")
    cost = info.get("avg_cost_usd", 0)
    sector = info.get("sector", "")

    # Name: prefer sector, then ticker itself
    name = sector if sector else ticker

    # Brief from holdings context
    parts = []
    if strategy:
        parts.append(strategy)
    if cost:
        parts.append(f"avg_cost=${cost:.0f}")
    brief = ", ".join(parts)

    signal = {
        "stock_code": ticker,
        "stock_name": name,
        "action": "BUY",
        "confidence": 0.7,
        "date": date.today().isoformat(),
        "category": category,
        "source": "alpha_push",
        "brief": brief,
    }
    if vol is not None:
        signal["volatility"] = vol
    return signal


def write_signal(signal: dict) -> Path:
    filename = signal["stock_code"].replace(".", "_") + ".yaml"
    target = SIGNAL_DIR / filename
    SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.dump(signal, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return target


# ── Entry point ──────────────────────────────────────────────────────────────

def run_push(cli_args: list[str]):
    """
    Main entry called from research_cli.py.

    Args:
        cli_args: ["all"] or ["NVDA"] or ["NVDA", "AAPL", "0700.HK"] or []
    """
    holdings = load_holdings()

    # Determine tickers
    if not cli_args or (len(cli_args) == 1 and cli_args[0].lower() == "all"):
        tickers = get_all_tickers(holdings)
        label = "all"
    else:
        tickers = [t.upper() if not any(c.isdigit() and "." in t for c in t) else t
                   for t in cli_args]
        # Preserve original case for HK/JP tickers like 0700.HK
        tickers = cli_args
        label = ", ".join(tickers)

    if not tickers:
        print("No tickers to push. Check Config/holdings.json")
        return

    print(f"\n{'='*60}")
    print(f"  AlphaSystem → TradingSystem Signal Push")
    print(f"  Tickers: {label} ({len(tickers)})")
    print(f"  Target:  {SIGNAL_DIR}")
    print(f"{'='*60}\n")

    results = []
    for ticker in tickers:
        print(f"  [{ticker:<12s}] ", end="", flush=True)
        vol = calc_volatility(ticker)
        vol_str = f"vol={vol:.1%}" if vol is not None else "vol=N/A"
        print(f"{vol_str:<12s} ", end="", flush=True)

        signal = build_signal(ticker, holdings, vol)
        path = write_signal(signal)
        cat = signal["category"]
        print(f"{cat:<8s} → {path.name}")
        results.append((ticker, vol, cat, path))

    print(f"\n{'='*60}")
    print(f"  Done: {len(results)} signals pushed")
    print(f"{'='*60}\n")


# Allow direct execution
if __name__ == "__main__":
    run_push(sys.argv[1:])
