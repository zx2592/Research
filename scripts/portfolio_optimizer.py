#!/usr/bin/env python3
"""
Portfolio Optimizer — optimalportfolios-powered rebalancing for AlphaSystem.

Computes target weights using various optimization methods (max diversification,
min volatility, max Sharpe, risk parity) and generates a concrete trade list.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import pandas as pd
import yfinance as yf
import optimalportfolios as op

from scripts.portfolio_metrics import load_portfolio, _YF_CACHE_DIR

yf.set_tz_cache_location(_YF_CACHE_DIR)

METHOD_MAP = {
    "max_diversification": op.PortfolioObjective.MAX_DIVERSIFICATION,
    "minvol": op.PortfolioObjective.MIN_VARIANCE,
    "maxsharpe": op.PortfolioObjective.MAXIMUM_SHARPE_RATIO,
    "riskparity": op.PortfolioObjective.EQUAL_RISK_CONTRIBUTION,
}


def fetch_prices(tickers: list[str], days: int = 252) -> pd.DataFrame:
    """Fetch historical close prices for given tickers."""
    from datetime import timedelta
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))
    prices = yf.download(tickers, start=start, end=end, progress=False)
    if isinstance(prices.columns, pd.MultiIndex):
        prices = prices["Close"]
    prices = prices.dropna(how="all").ffill()
    return prices.tail(days)


def optimize_portfolio(
    method: str = "max_diversification",
    max_position_pct: float = 15.0,
    min_cash_pct: float = 15.0,
    holdings_path: str | None = None,
    lookback_days: int = 252,
) -> dict:
    """Run portfolio optimization and generate rebalancing trades.

    Returns dict with: current_weights, target_weights, trades, metrics_before, metrics_after
    """
    holdings = load_portfolio(holdings_path)
    tickers = list(holdings.keys())

    # Fetch prices
    prices = fetch_prices(tickers, days=lookback_days)
    available_tickers = [t for t in tickers if t in prices.columns]

    if len(available_tickers) < 2:
        return {"error": "Not enough tickers with price data for optimization"}

    prices = prices[available_tickers]

    # Current weights from market values
    latest = prices.iloc[-1]
    market_values = {}
    total_mv = 0.0
    for t in available_tickers:
        if not pd.isna(latest[t]):
            mv = holdings[t]["shares"] * latest[t]
            market_values[t] = mv
            total_mv += mv

    # Reserve cash allocation
    investable_pct = (100.0 - min_cash_pct) / 100.0
    current_weights = {t: mv / total_mv for t, mv in market_values.items()}

    # Run optimization
    objective = METHOD_MAP.get(method)
    if objective is None:
        return {"error": f"Unknown method: {method}. Available: {list(METHOD_MAP.keys())}"}

    constraints = op.Constraints(
        min_weights=pd.Series({t: 0.0 for t in available_tickers}),
        max_weights=pd.Series({t: max_position_pct / 100.0 for t in available_tickers}),
    )

    try:
        # Estimate rolling EWMA covariance matrices
        import qis
        time_period = qis.TimePeriod(start=prices.index[0], end=prices.index[-1])
        covar_dict = op.estimate_rolling_ewma_covar(
            prices=prices,
            time_period=time_period,
            returns_freq="W-WED",
            rebalancing_freq="QE",
            span=52,
        )
        if not covar_dict:
            return {"error": "Covariance estimation returned no results (not enough data?)"}

        result = op.compute_rolling_optimal_weights(
            prices=prices,
            portfolio_objective=objective,
            constraints=constraints,
            covar_dict=covar_dict,
            rebalancing_freq="QE",
        )
        # Get the last row of weights
        if isinstance(result, pd.DataFrame) and len(result) > 0:
            raw_target = result.iloc[-1].to_dict()
        else:
            return {"error": "Optimization returned no results"}
    except Exception as e:
        return {"error": f"Optimization failed: {str(e)}"}

    # Scale target weights to investable portion (leave room for cash)
    target_weights = {}
    raw_sum = sum(abs(v) for v in raw_target.values() if not pd.isna(v))
    for t in available_tickers:
        raw_w = raw_target.get(t, 0.0)
        if pd.isna(raw_w):
            raw_w = 0.0
        target_weights[t] = (raw_w / raw_sum * investable_pct) if raw_sum > 0 else 0.0

    # Generate trade list
    trades = []
    for t in available_tickers:
        curr_w = current_weights.get(t, 0.0)
        tgt_w = target_weights.get(t, 0.0)
        delta_w = tgt_w - curr_w

        if abs(delta_w) < 0.005:  # Skip changes < 0.5%
            continue

        current_shares = holdings[t]["shares"]
        price = float(latest[t])
        target_mv = tgt_w * total_mv
        current_mv = market_values.get(t, 0.0)
        delta_mv = target_mv - current_mv
        delta_shares = int(delta_mv / price) if price > 0 else 0

        if delta_shares == 0:
            continue

        trades.append({
            "ticker": t,
            "action": "buy" if delta_shares > 0 else "sell",
            "shares": abs(delta_shares),
            "dollar_amount": round(abs(delta_mv), 2),
            "current_weight_pct": round(curr_w * 100, 2),
            "target_weight_pct": round(tgt_w * 100, 2),
            "delta_pct": round(delta_w * 100, 2),
            "strategy": holdings[t].get("strategy", "Unknown"),
        })

    trades.sort(key=lambda x: abs(x["delta_pct"]), reverse=True)

    # Compute before/after metrics
    returns = prices.pct_change().dropna()
    curr_w_arr = np.array([current_weights.get(t, 0.0) for t in available_tickers])
    tgt_w_arr = np.array([target_weights.get(t, 0.0) for t in available_tickers])
    cov = returns[available_tickers].cov().values * 252  # Annualized

    def _portfolio_stats(w):
        port_vol = float(np.sqrt(w @ cov @ w))
        port_ret = float(np.sum(w * returns[available_tickers].mean().values) * 252)
        sharpe = port_ret / port_vol if port_vol > 0 else 0.0
        hhi = float(np.sum((w * 100) ** 2))
        return {
            "annual_return_pct": round(port_ret * 100, 2),
            "annual_vol_pct": round(port_vol * 100, 2),
            "sharpe": round(sharpe, 3),
            "hhi": round(hhi, 0),
        }

    return {
        "method": method,
        "max_position_pct": max_position_pct,
        "min_cash_pct": min_cash_pct,
        "total_market_value": round(total_mv, 2),
        "tickers_count": len(available_tickers),
        "current_weights": {t: round(w * 100, 2) for t, w in current_weights.items()},
        "target_weights": {t: round(w * 100, 2) for t, w in target_weights.items()},
        "trades": trades,
        "metrics_before": _portfolio_stats(curr_w_arr),
        "metrics_after": _portfolio_stats(tgt_w_arr),
    }


def _json_serializable(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return round(float(obj), 6)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def main():
    parser = argparse.ArgumentParser(description="AlphaSystem Portfolio Optimizer")
    parser.add_argument("--method", choices=list(METHOD_MAP.keys()),
                        default="max_diversification", help="Optimization method")
    parser.add_argument("--max-position", type=float, default=15.0, help="Max single position %")
    parser.add_argument("--min-cash", type=float, default=15.0, help="Min cash allocation %")
    parser.add_argument("--days", type=int, default=252, help="Price lookback days")
    parser.add_argument("--holdings", type=str, default=None, help="Path to holdings.json")
    parser.add_argument("--output", type=str, default="json", help="Output format")
    args = parser.parse_args()

    result = optimize_portfolio(
        method=args.method,
        max_position_pct=args.max_position,
        min_cash_pct=args.min_cash,
        holdings_path=args.holdings,
        lookback_days=args.days,
    )

    print(json.dumps(result, indent=2, default=_json_serializable))


if __name__ == "__main__":
    main()
