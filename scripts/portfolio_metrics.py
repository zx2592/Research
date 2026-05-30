#!/usr/bin/env python3
"""
Portfolio Metrics Engine — quantstats-powered analytics for AlphaSystem.

Provides: performance metrics, contribution analysis, correlation matrix,
and HTML tearsheet generation. Used by /position and /optimize workflows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import pandas as pd
import quantstats as qs
import yfinance as yf

# --- yfinance cache ---
_YF_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache", "yfinance")
os.makedirs(_YF_CACHE_DIR, exist_ok=True)
yf.set_tz_cache_location(_YF_CACHE_DIR)

DEFAULT_HOLDINGS_PATH = os.path.join(PROJECT_ROOT, "Config", "holdings.json")
DEFAULT_BENCHMARK = "SPY"


def load_portfolio(holdings_path: str | None = None) -> dict:
    """Load holdings.json and return ticker -> {shares, cost, strategy, sector}."""
    path = holdings_path or DEFAULT_HOLDINGS_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    no_price = set(data.get("no_price_tickers", []))
    result = {}
    for ticker, info in data.get("tickers", {}).items():
        if ticker in no_price:
            continue
        result[ticker] = {
            "shares": info.get("total_shares", 0),
            "cost_basis": info.get("cost_basis_usd", 0),
            "strategy": info.get("strategy", "Unknown"),
            "sector": info.get("sector", "Unknown"),
        }
    return result


def fetch_portfolio_history(
    holdings: dict | None = None,
    days: int = 252,
    benchmark: str = DEFAULT_BENCHMARK,
) -> dict:
    """Fetch price history and compute portfolio-weighted daily returns.

    Returns dict with keys:
        portfolio_returns, benchmark_returns, weights, prices, ticker_returns
    """
    holdings = holdings or load_portfolio()
    tickers = list(holdings.keys())
    all_tickers = tickers + [benchmark]

    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))  # extra buffer for trading days

    prices = yf.download(all_tickers, start=start, end=end, progress=False)
    if isinstance(prices.columns, pd.MultiIndex):
        prices = prices["Close"]
    else:
        prices = prices[["Close"]].rename(columns={"Close": all_tickers[0]})

    prices = prices.dropna(how="all").ffill()

    # Compute current market values for weights
    latest_prices = prices.iloc[-1]
    market_values = {}
    total_mv = 0.0
    for t in tickers:
        if t in latest_prices and not pd.isna(latest_prices[t]):
            mv = holdings[t]["shares"] * latest_prices[t]
            market_values[t] = mv
            total_mv += mv

    weights = {t: mv / total_mv for t, mv in market_values.items()} if total_mv > 0 else {}

    # Daily returns
    returns = prices.pct_change().dropna()

    # Portfolio weighted returns
    portfolio_returns = pd.Series(0.0, index=returns.index)
    for t in tickers:
        if t in returns.columns and t in weights:
            portfolio_returns += returns[t] * weights[t]

    benchmark_returns = returns[benchmark] if benchmark in returns.columns else pd.Series(dtype=float)

    # Trim to requested days
    portfolio_returns = portfolio_returns.tail(days)
    benchmark_returns = benchmark_returns.tail(days) if len(benchmark_returns) > 0 else benchmark_returns

    ticker_returns = returns[tickers].tail(days) if len(returns) > 0 else pd.DataFrame()

    return {
        "portfolio_returns": portfolio_returns,
        "benchmark_returns": benchmark_returns,
        "weights": weights,
        "prices": prices[tickers].tail(days),
        "ticker_returns": ticker_returns,
        "market_values": market_values,
        "total_mv": total_mv,
    }


def compute_metrics(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> dict:
    """Compute key quantstats metrics."""
    pr = portfolio_returns
    br = benchmark_returns if len(benchmark_returns) > 0 else None

    metrics = {
        "cagr": _safe(qs.stats.cagr, pr),
        "sharpe": _safe(qs.stats.sharpe, pr),
        "sortino": _safe(qs.stats.sortino, pr),
        "max_drawdown": _safe(qs.stats.max_drawdown, pr),
        "calmar": _safe(qs.stats.calmar, pr),
        "volatility": _safe(qs.stats.volatility, pr),
        "win_rate": _safe(qs.stats.win_rate, pr),
        "best_day": _safe(qs.stats.best, pr),
        "worst_day": _safe(qs.stats.worst, pr),
        "var_95": _safe(qs.stats.var, pr),
        "cvar_95": _safe(qs.stats.cvar, pr),
        "ytd_return": _compute_period_return(pr, "ytd"),
        "mtd_return": _compute_period_return(pr, "mtd"),
    }

    if br is not None and len(br) > 0:
        metrics["beta"] = _safe(qs.stats.greeks, pr, br, item="beta")
        metrics["alpha"] = _safe(qs.stats.greeks, pr, br, item="alpha")
        metrics["information_ratio"] = _safe(qs.stats.information_ratio, pr, br)
        metrics["benchmark_cagr"] = _safe(qs.stats.cagr, br)
        metrics["benchmark_sharpe"] = _safe(qs.stats.sharpe, br)
        metrics["benchmark_max_drawdown"] = _safe(qs.stats.max_drawdown, br)
        metrics["benchmark_volatility"] = _safe(qs.stats.volatility, br)

    return metrics


def _compute_period_return(returns: pd.Series, period: str) -> float | None:
    """Compute YTD or MTD return from a daily returns series."""
    try:
        now = returns.index[-1]
        if period == "ytd":
            start = pd.Timestamp(year=now.year, month=1, day=1, tz=now.tz if hasattr(now, "tz") else None)
        elif period == "mtd":
            start = pd.Timestamp(year=now.year, month=now.month, day=1, tz=now.tz if hasattr(now, "tz") else None)
        else:
            return None
        subset = returns[returns.index >= start]
        if subset.empty:
            return None
        return float((1 + subset).prod() - 1)
    except Exception:
        return None


def _safe(func, *args, item=None, **kwargs):
    """Call a quantstats function and return float or None on error."""
    try:
        result = func(*args, **kwargs)
        if item and isinstance(result, pd.Series):
            result = result.get(item, result.iloc[0] if len(result) > 0 else None)
        if isinstance(result, (pd.Series, pd.DataFrame)):
            result = result.iloc[0] if len(result) > 0 else None
        if result is not None and hasattr(result, "item"):
            return float(result.item())
        return float(result) if result is not None else None
    except Exception:
        return None


def compute_correlation(prices: pd.DataFrame, top_n: int = 10) -> list[dict]:
    """Compute correlation matrix and return top N most correlated pairs."""
    returns = prices.pct_change().dropna()
    if returns.empty or returns.shape[1] < 2:
        return []

    corr = returns.corr()
    pairs = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            val = corr.iloc[i, j]
            if not pd.isna(val):
                pairs.append({
                    "ticker_a": cols[i],
                    "ticker_b": cols[j],
                    "correlation": round(float(val), 3),
                })

    pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return pairs[:top_n]


def compute_contribution(
    weights: dict,
    ticker_returns: pd.DataFrame,
    period_days: int = 30,
) -> list[dict]:
    """Compute each ticker's contribution to portfolio return over period."""
    recent = ticker_returns.tail(period_days)
    if recent.empty:
        return []

    results = []
    total_contribution = 0.0
    for ticker, weight in weights.items():
        if ticker not in recent.columns:
            continue
        ticker_return = float((1 + recent[ticker]).prod() - 1)
        contribution = weight * ticker_return
        total_contribution += contribution
        results.append({
            "ticker": ticker,
            "weight_pct": round(weight * 100, 2),
            "period_return_pct": round(ticker_return * 100, 2),
            "contribution_bps": round(contribution * 10000, 1),
        })

    # Add contribution_pct (share of total return)
    for r in results:
        if total_contribution != 0:
            r["contribution_pct"] = round(r["contribution_bps"] / (total_contribution * 10000) * 100, 1)
        else:
            r["contribution_pct"] = 0.0

    results.sort(key=lambda x: x["contribution_bps"], reverse=True)
    return results


def generate_tearsheet(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    output_path: str,
) -> str:
    """Generate quantstats HTML tearsheet."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    qs.reports.html(
        portfolio_returns,
        benchmark=benchmark_returns if len(benchmark_returns) > 0 else None,
        output=output_path,
        title="AlphaSystem Portfolio",
    )
    return output_path


def _json_serializable(obj):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return round(float(obj), 6)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def main():
    parser = argparse.ArgumentParser(description="AlphaSystem Portfolio Metrics Engine")
    parser.add_argument("--mode", choices=["metrics", "tearsheet", "correlation", "contribution", "snapshot"],
                        required=True, help="Analysis mode")
    parser.add_argument("--days", type=int, default=252, help="Lookback period in trading days")
    parser.add_argument("--period", type=int, default=30, help="Period for contribution analysis (days)")
    parser.add_argument("--output", type=str, default="json", help="Output: 'json' for stdout or file path")
    parser.add_argument("--holdings", type=str, default=None, help="Path to holdings.json")
    parser.add_argument("--benchmark", type=str, default=DEFAULT_BENCHMARK, help="Benchmark ticker")
    args = parser.parse_args()

    holdings = load_portfolio(args.holdings)
    data = fetch_portfolio_history(holdings, days=args.days, benchmark=args.benchmark)

    if args.mode == "snapshot":
        result = {
            "total_market_value": data["total_mv"],
            "weights": {t: round(w * 100, 2) for t, w in data["weights"].items()},
            "market_values": {t: round(v, 2) for t, v in data["market_values"].items()},
            "holdings_count": len(holdings),
        }
    elif args.mode == "metrics":
        result = compute_metrics(data["portfolio_returns"], data["benchmark_returns"])
    elif args.mode == "correlation":
        result = compute_correlation(data["prices"])
    elif args.mode == "contribution":
        result = compute_contribution(data["weights"], data["ticker_returns"], period_days=args.period)
    elif args.mode == "tearsheet":
        output_path = args.output if args.output != "json" else os.path.join(
            PROJECT_ROOT, "Reports", datetime.now().strftime("%Y%m%d"),
            f"{datetime.now().strftime('%Y%m%d')}_Position_Tearsheet.html",
        )
        path = generate_tearsheet(data["portfolio_returns"], data["benchmark_returns"], output_path)
        print(json.dumps({"tearsheet_path": path}))
        return

    print(json.dumps(result, indent=2, default=_json_serializable))


if __name__ == "__main__":
    main()
