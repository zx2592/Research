#!/usr/bin/env python3
"""
Valuation Math — 反向 DCF 与安全边际的确定性计算。

存在的理由是分工：**可计算、可判真假的东西不该交给模型心算**。
隐含增长率、终值占比、安全边际价、敏感性矩阵都有闭式解或可数值求解，
让 LLM 口算的结果既不可复现（同一标的两次跑出不同数字），也无法回归测试。

本脚本只做算术与量纲检查，不做投资判断：
「隐含增长率是 32%」是算出来的，「32% 是否超过行业天花板」由报告作者判断。

用法：
    python scripts/valuation_math.py --market-cap 3.2e12 --fcf 6.0e10
    python scripts/valuation_math.py --price 178.5 --shares 1.55e10 --fcf 6.0e10 \
        --discount-rate 0.10 --terminal-growth 0.03 --years 10

输出 JSON 到 stdout。检查未通过时 exit code 为 1（供 workflow 当硬门用）。
仅依赖标准库，任何环境都能跑。
"""

from __future__ import annotations

import argparse
import json
import sys

# 合理区间：超出即告警。不是硬性真理，是「越界必须在报告里解释」的触发线。
WACC_SANE_RANGE = (0.05, 0.20)
TERMINAL_GROWTH_SANE_RANGE = (0.0, 0.05)
TV_SHARE_SANE_RANGE = (0.40, 0.80)
# 十年维度上能维持 40%+ 年化自由现金流增长的公司屈指可数，越线要求报告正面回应
IMPLIED_GROWTH_ALERT = 0.40

# 反向求解的搜索区间与精度
_GROWTH_SEARCH_RANGE = (-0.90, 3.00)
_BISECTION_ITERATIONS = 200


def enterprise_value(
    fcf0: float,
    growth: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> dict:
    """两阶段 DCF：显式期按 growth 增长，之后按 terminal_growth 永续。

    返回企业价值及其构成，便于检查终值占比这一最常见的 DCF 失真来源。
    """
    if discount_rate <= terminal_growth:
        raise ValueError(
            f"discount_rate ({discount_rate:.4f}) must exceed terminal_growth "
            f"({terminal_growth:.4f}); otherwise terminal value is infinite."
        )

    pv_explicit = 0.0
    cash_flow = fcf0
    for year in range(1, years + 1):
        cash_flow = fcf0 * (1.0 + growth) ** year
        pv_explicit += cash_flow / (1.0 + discount_rate) ** year

    terminal_value = cash_flow * (1.0 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1.0 + discount_rate) ** years

    total = pv_explicit + pv_terminal
    return {
        "enterprise_value": total,
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_terminal,
        "terminal_value_undiscounted": terminal_value,
        "tv_share_of_ev": (pv_terminal / total) if total else None,
    }


def solve_implied_growth(
    target_ev: float,
    fcf0: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> float | None:
    """反解「要撑起当前价格，显式期必须实现多高的年化增长」。

    EV 对 growth 单调递增，用二分法即可。无解（目标价格低于零增长下限或
    高于搜索上限）时返回 None，由调用方如实申报，而不是给一个凑出来的数字。
    """
    if fcf0 <= 0:
        return None

    low, high = _GROWTH_SEARCH_RANGE

    def ev_at(g: float) -> float:
        return enterprise_value(fcf0, g, discount_rate, terminal_growth, years)["enterprise_value"]

    if ev_at(low) > target_ev or ev_at(high) < target_ev:
        return None

    for _ in range(_BISECTION_ITERATIONS):
        mid = (low + high) / 2.0
        if ev_at(mid) < target_ev:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def sensitivity_grid(
    fcf0: float,
    growth: float,
    discount_rate: float,
    terminal_growth: float,
    years: int,
    net_debt: float,
    shares: float | None,
) -> dict:
    """折现率 × 增长率的敏感性矩阵。

    单点估值给人虚假的精确感；矩阵让「结论对假设有多敏感」变成可见的事实。
    """
    rate_steps = [discount_rate - 0.02, discount_rate - 0.01, discount_rate,
                  discount_rate + 0.01, discount_rate + 0.02]
    growth_steps = [growth - 0.10, growth - 0.05, growth, growth + 0.05, growth + 0.10]

    rows = []
    for rate in rate_steps:
        if rate <= terminal_growth:
            # 折现率跌破永续增长率时模型本身失效，如实留空而不是填一个大数
            rows.append({"discount_rate": round(rate, 4), "values": [None] * len(growth_steps)})
            continue
        values = []
        for g in growth_steps:
            ev = enterprise_value(fcf0, g, rate, terminal_growth, years)["enterprise_value"]
            equity = ev - net_debt
            values.append(round(equity / shares, 4) if shares else round(equity, 2))
        rows.append({"discount_rate": round(rate, 4), "values": values})

    return {
        "unit": "per_share" if shares else "equity_value",
        "growth_steps": [round(g, 4) for g in growth_steps],
        "rows": rows,
    }


def run_checks(
    discount_rate: float,
    terminal_growth: float,
    tv_share: float | None,
    implied_growth: float | None,
    fcf0: float,
) -> list[dict]:
    """量纲与合理性检查。FAIL 表示模型在数学上无效，WARN 表示需要在报告里解释。"""
    checks: list[dict] = []

    def add(level: str, name: str, message: str) -> None:
        checks.append({"level": level, "check": name, "message": message})

    if terminal_growth >= discount_rate:
        add("FAIL", "terminal_growth_below_discount_rate",
            f"永续增长率 {terminal_growth:.2%} >= 折现率 {discount_rate:.2%}，"
            f"终值为无穷大，模型在数学上无效。")

    if fcf0 <= 0:
        add("FAIL", "positive_base_cash_flow",
            f"基期自由现金流为 {fcf0:,.0f}（非正），反向 DCF 不适用。"
            f"请改用 EV/Sales、EV/GP 或分部估值，并在报告中说明原因。")

    lo, hi = WACC_SANE_RANGE
    if not (lo <= discount_rate <= hi):
        add("WARN", "discount_rate_in_sane_range",
            f"折现率 {discount_rate:.2%} 落在常见区间 [{lo:.0%}, {hi:.0%}] 之外，需说明依据。")

    lo, hi = TERMINAL_GROWTH_SANE_RANGE
    if not (lo <= terminal_growth <= hi):
        add("WARN", "terminal_growth_in_sane_range",
            f"永续增长率 {terminal_growth:.2%} 落在 [{lo:.0%}, {hi:.0%}] 之外；"
            f"长期高于名义 GDP 增速意味着公司最终会大于整个经济体。")

    if tv_share is not None:
        lo, hi = TV_SHARE_SANE_RANGE
        if not (lo <= tv_share <= hi):
            add("WARN", "terminal_value_share",
                f"终值占企业价值 {tv_share:.1%}，落在 [{lo:.0%}, {hi:.0%}] 之外；"
                f"占比过高说明估值几乎全部依赖永续假设，显式期预测意义有限。")

    if implied_growth is None:
        add("WARN", "implied_growth_solvable",
            "在给定假设下无法解出隐含增长率（当前价格超出搜索区间）；"
            "报告中应如实说明，不得给出编造的隐含增长率。")
    elif implied_growth > IMPLIED_GROWTH_ALERT:
        add("WARN", "implied_growth_plausible",
            f"隐含年化增长率 {implied_growth:.1%} 超过 {IMPLIED_GROWTH_ALERT:.0%}；"
            f"报告必须正面回答：历史上有同体量公司维持过这个速度吗？")

    return checks


def analyze(args: argparse.Namespace) -> dict:
    shares = args.shares if args.shares and args.shares > 0 else None

    if args.market_cap:
        market_cap = args.market_cap
    elif args.price and shares:
        market_cap = args.price * shares
    else:
        raise SystemExit("必须提供 --market-cap，或同时提供 --price 与 --shares")

    target_ev = market_cap + args.net_debt

    implied_growth = solve_implied_growth(
        target_ev=target_ev,
        fcf0=args.fcf,
        discount_rate=args.discount_rate,
        terminal_growth=args.terminal_growth,
        years=args.years,
    ) if args.fcf > 0 and args.discount_rate > args.terminal_growth else None

    breakdown = None
    tv_share = None
    if implied_growth is not None:
        breakdown = enterprise_value(
            args.fcf, implied_growth, args.discount_rate, args.terminal_growth, args.years
        )
        tv_share = breakdown["tv_share_of_ev"]

    # 安全边际：实际增长只有隐含增长一半时，股价应该在哪里
    margin_of_safety = None
    if implied_growth is not None:
        half_growth = implied_growth / 2.0
        mos = enterprise_value(
            args.fcf, half_growth, args.discount_rate, args.terminal_growth, args.years
        )
        equity = mos["enterprise_value"] - args.net_debt
        margin_of_safety = {
            "growth_assumption": round(half_growth, 6),
            "equity_value": round(equity, 2),
            "value_per_share": round(equity / shares, 4) if shares else None,
            "downside_vs_current": round(equity / market_cap - 1.0, 6) if market_cap else None,
        }

    result = {
        "inputs": {
            "market_cap": market_cap,
            "net_debt": args.net_debt,
            "enterprise_value_target": target_ev,
            "fcf_base": args.fcf,
            "discount_rate": args.discount_rate,
            "terminal_growth": args.terminal_growth,
            "years": args.years,
            "shares": shares,
            "price": args.price,
        },
        "implied_growth": {
            "cagr": round(implied_growth, 6) if implied_growth is not None else None,
            "cagr_pct": f"{implied_growth:.2%}" if implied_growth is not None else None,
            "solved": implied_growth is not None,
        },
        "value_breakdown": {
            "pv_explicit": round(breakdown["pv_explicit"], 2) if breakdown else None,
            "pv_terminal": round(breakdown["pv_terminal"], 2) if breakdown else None,
            "tv_share_of_ev": round(tv_share, 6) if tv_share is not None else None,
        },
        "margin_of_safety": margin_of_safety,
    }

    if args.assumed_growth is not None and args.discount_rate > args.terminal_growth:
        fair = enterprise_value(
            args.fcf, args.assumed_growth, args.discount_rate, args.terminal_growth, args.years
        )
        equity = fair["enterprise_value"] - args.net_debt
        result["fair_value_at_assumed_growth"] = {
            "growth_assumption": args.assumed_growth,
            "equity_value": round(equity, 2),
            "value_per_share": round(equity / shares, 4) if shares else None,
            "upside_vs_current": round(equity / market_cap - 1.0, 6) if market_cap else None,
        }

    if implied_growth is not None and not args.no_sensitivity:
        result["sensitivity"] = sensitivity_grid(
            fcf0=args.fcf,
            growth=implied_growth,
            discount_rate=args.discount_rate,
            terminal_growth=args.terminal_growth,
            years=args.years,
            net_debt=args.net_debt,
            shares=shares,
        )

    checks = run_checks(
        discount_rate=args.discount_rate,
        terminal_growth=args.terminal_growth,
        tv_share=tv_share,
        implied_growth=implied_growth,
        fcf0=args.fcf,
    )
    result["checks"] = checks
    result["status"] = "fail" if any(c["level"] == "FAIL" for c in checks) else (
        "warn" if any(c["level"] == "WARN" for c in checks) else "success"
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="反向 DCF 与安全边际计算（确定性，供 /deep /value /buy 调用）"
    )
    parser.add_argument("--market-cap", type=float, default=0.0, help="当前市值（与 --price/--shares 二选一）")
    parser.add_argument("--price", type=float, default=0.0, help="当前股价")
    parser.add_argument("--shares", type=float, default=0.0, help="总股本，给出后输出每股价值")
    parser.add_argument("--fcf", type=float, required=True, help="基期自由现金流（或可持续净利润）")
    parser.add_argument("--net-debt", type=float, default=0.0, help="净债务（净现金为负值）")
    parser.add_argument("--discount-rate", type=float, default=0.10, help="折现率 / WACC，默认 0.10")
    parser.add_argument("--terminal-growth", type=float, default=0.03, help="永续增长率，默认 0.03")
    parser.add_argument("--years", type=int, default=10, help="显式预测期年数，默认 10")
    parser.add_argument("--assumed-growth", type=float, default=None,
                        help="给定增长率时额外输出对应的合理价值")
    parser.add_argument("--no-sensitivity", action="store_true", help="不输出敏感性矩阵")
    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """把 `--net-debt -5e9` 改写成 `--net-debt=-5e9`。

    argparse 会把以 `-` 开头的负数当成选项名。净债务为负（净现金）、
    自由现金流为负都是正常输入，调用方是模型时更不该被这种语法细节绊住。
    """
    normalized: list[str] = []
    skip_next = False
    for index, token in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        following = argv[index + 1] if index + 1 < len(argv) else None
        if token.startswith("--") and "=" not in token and following and following.startswith("-"):
            try:
                float(following)
            except ValueError:
                normalized.append(token)
                continue
            normalized.append(f"{token}={following}")
            skip_next = True
            continue
        normalized.append(token)
    return normalized


def main() -> int:
    args = build_parser().parse_args(_normalize_argv(sys.argv[1:]))
    result = analyze(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
