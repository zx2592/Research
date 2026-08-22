"""价格/财务多源交叉验证 — 纯逻辑，无 I/O，便于单测。

交叉验证的价值不在「取到两个数」，而在「这两个数是不是同一份数据的两个门面」。
腾讯行情、东方财富、新浪、同花顺、雪球都在转发同一份交易所行情——互相比对
得到 0.00% 偏差，看起来像最高可信度，实际上一个来源都没交叉到。

因此本模块按**来源族 (family)** 而不是来源名判断独立性：
只有跨族的两个读数才算交叉，同族之间再多也按单源处理。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

# --- 来源族 -----------------------------------------------------------------
# 同一族 = 同一条数据链路的不同门面，互相比对不构成交叉验证。
SOURCE_FAMILIES: dict[str, str] = {
    # 国际行情供应商链路（Yahoo / Refinitiv / 彭博一系）
    "fetch_market_prices": "intl-vendor",
    "yfinance": "intl-vendor",
    "yahoo": "intl-vendor",
    # 中国大陆行情转发链路（都在转发交易所 Level-1）
    "tencent": "cn-exchange-relay",
    "eastmoney": "cn-exchange-relay",
    "sina": "cn-exchange-relay",
    "ths": "cn-exchange-relay",
    "xueqiu": "cn-exchange-relay",
    "tushare": "cn-exchange-relay",
    # 台股
    "finmind": "tw-vendor",
    "goodinfo": "tw-vendor",
    # 一手披露
    "exchange": "primary-disclosure",
    "cninfo": "primary-disclosure",
    "hkexnews": "primary-disclosure",
    "sec": "primary-disclosure",
    "company-ir": "primary-disclosure",
}

UNKNOWN_FAMILY = "unknown"

# --- 偏差分级（对齐 ai-berkshire 的财务数据交叉验证规范）--------------------
# ≤1%   一致，取共识值
# 1~5%  存在差异，须注明两个数值与可能原因（汇率 / 会计口径 / 更新滞后）
# >5%   重大差异，必须回原始披露核实，不得直接使用
MINOR_DIVERGENCE_PCT = 1.0
MAJOR_DIVERGENCE_PCT = 5.0


def family_of(source_name: str) -> str:
    """返回来源所属的族；未登记的来源按 unknown 处理（不与任何族合并）。"""
    if not source_name:
        return UNKNOWN_FAMILY
    key = source_name.strip().lower()
    # 允许 "yfinance:urllib_direct" 这类带方法后缀的来源名
    base = key.split(":", 1)[0]
    return SOURCE_FAMILIES.get(base, UNKNOWN_FAMILY)


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)


def grade_deviation(deviation_pct: float) -> str:
    """把偏差百分比映射到三档：consistent / minor / major。"""
    if deviation_pct <= MINOR_DIVERGENCE_PCT:
        return "consistent"
    if deviation_pct <= MAJOR_DIVERGENCE_PCT:
        return "minor"
    return "major"


_GRADE_MARK = {"consistent": "✅", "minor": "⚠️", "major": "❌"}


def build_consensus(
    samples: Iterable[dict],
    tolerance_pct: float = MINOR_DIVERGENCE_PCT,
    label: str = "价格",
    unit: str = "",
    allow_identical: bool = False,
) -> dict:
    """对多个来源的同一指标做交叉验证。

    samples: [{"source": str, "value": number, "fetched_at": str|None}, ...]
    allow_identical: 两个跨族来源数值完全相同时是否仍判为已交叉。默认 False——
        两个真正独立的来源（一家用最新成交、一家用官方收盘）几乎不可能分毫不差，
        完全相同更可能是同一份数据的两个门面，确认不了就按单源处理。

    返回结构里的 `verdict` 是一句可以**原样抄进报告结论区**的话。
    """
    rows = []
    for sample in samples or []:
        value = _to_decimal(sample.get("value"))
        if value is None:
            continue
        source = str(sample.get("source") or "unknown")
        rows.append({
            "source": source,
            "family": family_of(source),
            "value": value,
            "fetched_at": sample.get("fetched_at"),
        })

    if not rows:
        return {
            "label": label,
            "passed": False,
            "grade": "no_data",
            "consensus": None,
            "max_deviation_pct": None,
            "sources": [],
            "families": [],
            "independent_family_count": 0,
            "identical_values": False,
            "verdict": f"{label}证据：未取到任何来源的读数——本次不得给出依赖该数字的结论",
            "reason": "no numeric sample",
        }

    consensus = _median([row["value"] for row in rows])
    max_deviation = 0.0
    for row in rows:
        if consensus == 0:
            deviation = 0.0
        else:
            deviation = float(abs(row["value"] - consensus) / abs(consensus) * 100)
        row["deviation_pct"] = round(deviation, 6)
        row["grade"] = grade_deviation(deviation)
        row["mark"] = _GRADE_MARK[row["grade"]]
        max_deviation = max(max_deviation, deviation)

    families = sorted({row["family"] for row in rows if row["family"] != UNKNOWN_FAMILY})
    unknown_count = sum(1 for row in rows if row["family"] == UNKNOWN_FAMILY)
    # 未登记的来源各自算独立一族（宁可高估独立性也不要把它并进已知族）
    independent_family_count = len(families) + unknown_count

    distinct_values = {str(row["value"]) for row in rows}
    identical_values = len(rows) > 1 and len(distinct_values) == 1

    grade = grade_deviation(max_deviation)
    passed = (
        independent_family_count >= 2
        and max_deviation <= tolerance_pct
        and (allow_identical or not identical_values)
    )

    if independent_family_count < 2:
        reason = "所有读数来自同一来源族，互相比对不构成交叉"
        grade = "single_family"
    elif identical_values and not allow_identical:
        reason = "跨族读数完全相同（偏差 0.00%），疑似同一份数据的两个门面，按单源处理"
        grade = "suspect_same_source"
    elif max_deviation > tolerance_pct:
        reason = f"跨族读数偏差 {max_deviation:.2f}% 超过容差 {tolerance_pct:.2f}%"
    else:
        reason = "跨族读数在容差内一致"

    return {
        "label": label,
        "passed": passed,
        "grade": grade,
        "consensus": float(consensus),
        "unit": unit,
        "tolerance_pct": tolerance_pct,
        "max_deviation_pct": round(max_deviation, 6),
        "sources": [
            {
                "source": row["source"],
                "family": row["family"],
                "value": float(row["value"]),
                "deviation_pct": row["deviation_pct"],
                "grade": row["grade"],
                "mark": row["mark"],
                "fetched_at": row["fetched_at"],
            }
            for row in rows
        ],
        "families": families + ([UNKNOWN_FAMILY] * unknown_count),
        "independent_family_count": independent_family_count,
        "identical_values": identical_values,
        "reason": reason,
        "verdict": _render_verdict(
            label=label,
            unit=unit,
            consensus=float(consensus),
            rows=rows,
            passed=passed,
            grade=grade,
            max_deviation=max_deviation,
            reason=reason,
        ),
    }


def _render_verdict(
    *,
    label: str,
    unit: str,
    consensus: float,
    rows: list[dict],
    passed: bool,
    grade: str,
    max_deviation: float,
    reason: str,
) -> str:
    """生成可直接抄进报告结论区的一行价格/数据证据。"""
    stamp = ""
    stamps = [row.get("fetched_at") for row in rows if row.get("fetched_at")]
    if stamps:
        stamp = f"，{stamps[0]}"
    names = " / ".join(row["source"] for row in rows)
    value_text = f"{consensus:g}{unit}"

    if passed:
        return (
            f"{label}证据：{value_text} · {len(rows)} 源已交叉，"
            f"偏差 {max_deviation:.2f}%（{names}{stamp}）"
        )
    if grade == "single_family":
        return (
            f"{label}证据：{value_text} · 单源未交叉（{names}{stamp}）"
            f"——{reason}；本次不得给出目标价、止损与盈亏比"
        )
    if grade == "suspect_same_source":
        return (
            f"{label}证据：{value_text} · 疑似同源，按单源处理（{names}{stamp}）"
            f"——{reason}；本次不得给出目标价、止损与盈亏比"
        )
    mark = _GRADE_MARK.get(grade, "⚠️")
    return (
        f"{label}证据：{value_text} · {mark} 来源不一致，偏差 {max_deviation:.2f}%"
        f"（{names}{stamp}）——{reason}；须并列写出各来源数值并说明取舍"
    )


def verify_market_cap(price, shares, reported_cap, currency: str = "", tolerance_pct: float = 5.0) -> dict:
    """验算市值 = 股价 × 总股本，与披露市值对照。

    增发、回购、ADR 存托比率、库存股都会让「披露市值」和「股价×股本」对不上；
    偏差超过容差就是一个该回原始披露核实的信号，而不是四舍五入误差。
    """
    p = _to_decimal(price)
    s = _to_decimal(shares)
    r = _to_decimal(reported_cap)
    if p is None or s is None or r is None:
        return {"passed": False, "error": "price / shares / reported_cap 必须都是数字"}

    calculated = p * s
    if r == 0:
        return {"passed": False, "error": "reported_cap 不能为 0"}

    deviation = float(abs(calculated - r) / abs(r) * 100)
    passed = deviation <= tolerance_pct
    return {
        "passed": passed,
        "currency": currency,
        "calculated_cap": float(calculated),
        "reported_cap": float(r),
        "deviation_pct": round(deviation, 6),
        "tolerance_pct": tolerance_pct,
        "verdict": (
            f"市值验算：{'✅ 一致' if passed else '❌ 偏差超标'} "
            f"（股价×股本 = {float(calculated):,.0f}{currency}，"
            f"披露 = {float(r):,.0f}{currency}，偏差 {deviation:.2f}%）"
            + ("" if passed else "——请核对总股本口径：增发/回购/库存股/ADR 存托比率")
        ),
    }
