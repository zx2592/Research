#!/usr/bin/env python3
"""
Report Generator - Report Generation & Saving (Core Format)
v2.0

Standard format based on Core Three-Layer Architecture:
- 市场洞察报告 → Reports/Internal_Report/YYYY-MM/
- 投资雷达 → Config/ai建议/
- 日报/快报 → Reports/YYYYMMDD/
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_report_paths():
    """获取当前日期对应的报告路径"""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    date_dash = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    return {
        "raw_data_dir": os.path.join(PROJECT_ROOT, "Reports", "Raw_Data", month_str),
        "internal_report_dir": os.path.join(PROJECT_ROOT, "Reports", "Internal_Report", month_str),
        "daily_dir": os.path.join(PROJECT_ROOT, "Reports", date_str),
        "radar_dir": os.path.join(PROJECT_ROOT, "Config", "ai建议"),
        "raw_data_file": os.path.join(PROJECT_ROOT, "Reports", "Raw_Data", month_str, f"financial_data_{date_str}.json"),
        "insight_file": os.path.join(PROJECT_ROOT, "Reports", "Internal_Report", month_str, f"{date_dash}_Internal_Report.md"),
        "radar_file": os.path.join(PROJECT_ROOT, "Config", "ai建议", f"投资雷达_{date_dash}.md"),
        "date_str": date_str,
        "date_dash": date_dash,
        "month_str": month_str,
    }


def save_report(content, report_type, ticker=None, suffix=None):
    """
    保存报告到对应目录

    Args:
        content: 报告内容 (markdown)
        report_type: "insight" | "radar" | "deep" | "quick" | "value" | "verify" | "update" | "scan"
        ticker: 股票代码 (可选)
        suffix: 自定义文件后缀 (可选)
    """
    paths = get_report_paths()

    if report_type == "insight":
        filepath = paths["insight_file"]
    elif report_type == "radar":
        filepath = paths["radar_file"]
    elif report_type in ("deep", "quick", "value", "verify", "update", "scan"):
        dir_path = paths["daily_dir"]
        ticker_str = f"_{ticker}" if ticker else ""
        suffix_str = f"_{suffix}" if suffix else f"_{report_type.capitalize()}"
        filename = f"{paths['date_str']}{ticker_str}{suffix_str}.md"
        filepath = os.path.join(dir_path, filename)
    else:
        filepath = os.path.join(paths["daily_dir"], f"{paths['date_str']}_{report_type}.md")

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Report saved: %s", filepath)
    return filepath


def save_raw_data(data, date_str=None):
    """保存原始数据到 Raw_Data 目录"""
    import json
    paths = get_report_paths()
    filepath = paths["raw_data_file"]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Raw data saved: %s", filepath)
    return filepath
