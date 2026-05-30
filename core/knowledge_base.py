#!/usr/bin/env python3
"""
Knowledge Base - /add 知识库功能
v2.0

将研究报告的核心洞察提取为知识卡片，保存到:
1. Memory_Layer/Knowledge_Base/ (项目内)
2. Obsidian Vault (可选, 通过 OBSIDIAN_VAULT_PATH 配置)
"""

import os
import tempfile
import logging
from datetime import datetime

from core import config  # noqa: F401 — ensures load_dotenv runs once

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR    = os.path.join(PROJECT_ROOT, "Memory_Layer", "Knowledge_Base")
KB_INDEX  = os.path.join(KB_DIR, "KB_INDEX.md")  # 新索引（与 Agent 路径一致）
# 兼容旧版本，保留 README 路径不变
INDEX_FILE = os.path.join(KB_DIR, "README.md")


def save_knowledge_card(title, tags, card_type, summary, insights, strategy, source_path,
                        ticker="N/A", status="纯研究"):
    """
    生成并保存知识卡片（YAML Front Matter 新格式，与 Agent 工作流一致）

    Args:
        title:       卡片标题 (e.g., "MCO信用评级")
        tags:        标签列表 (e.g., ["\u7f8e\u80a1", "\u91d1\u878d\u6570\u636e"])
        card_type:   Company | Theme | Macro | MarketEvent
        summary:     摘要（将成为\u201c核心逻辑\u201d节）
        insights:    核心洞察列表（将成为\u201c最新边际变化\u201d节）
        strategy:    可执行策略（将成为\u201c风险提示\u201d节）
        source_path: 原始报告路径
        ticker:      股票代码（行业/宏观类填 N/A）
        status:      持有中 | 已退出 | 观察池 | 纯研究
    """
    date_str  = datetime.now().strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    filename  = f"{ticker}_{date_str}.md" if ticker != "N/A" else f"{title}_{date_str}.md"
    filepath  = os.path.join(KB_DIR, filename)

    # 标签列表（YAML 格式）
    tags_yaml = ", ".join(tags)

    # 样本数据锁（从 insights 中提取数字，暂用占位符）
    insights_md = "\n".join([f"- {i}" for i in insights])

    content = f"""---
ticker: {ticker}
type: {card_type}
status: {status}
tags: [{tags_yaml}]
last_updated: {today_str}
linked_report: {source_path}
---

# {title} 知识卡片

## 1. 核心逻辑（一句话）
> {summary}

## 2. 关键数据锁点
| 指标 | 数值 | 更新日期 |
| :--- | :--- | :--- |
| (请补充关键财务指标) | ... | {today_str} |

## 3. 最新边际变化
{insights_md}

## 4. 风险提示
{strategy}

## 5. 历史分析记录
- [{today_str} 初次建档]({source_path})
"""

    os.makedirs(KB_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Knowledge card saved: %s", filepath)

    # 更新新索引 KB_INDEX.md
    _update_kb_index(filename, ticker, title, tags, card_type, today_str, source_path)

    # 尝试同步到 Obsidian
    _sync_to_obsidian(filepath, filename)

    return filepath


def _update_kb_index(filename, ticker, title, tags, card_type, today_str, source_path):
    """更新 KB_INDEX.md（与 Agent /add 工作流保持一致）"""
    os.makedirs(KB_DIR, exist_ok=True)

    # 判断分类：个股 / 行业主题 / 宏观事件
    if card_type in ("Company",):
        section = "一、个股档案"
        keywords = f"{ticker}, {title}"
    elif card_type in ("Theme",):
        section = "二、行业/主题研究"
        keywords = ", ".join(tags[:3])
    else:  # Macro, MarketEvent
        section = "三、宏观/市场事件"
        keywords = ", ".join(tags[:3])

    tags_str = ", ".join(tags)
    new_row = (f"| {keywords} | {title} | {tags_str} | {today_str} "
               f"| [{filename}]({filename}) | {source_path} |\n")

    if not os.path.exists(KB_INDEX):
        # 首次创建 - 建立基础结构
        with open(KB_INDEX, "w", encoding="utf-8") as f:
            f.write("# Knowledge Base Index\n\n")
            f.write(f"**最后更新**: {today_str}\n\n")
            f.write("## 一、个股档案\n\n")
            f.write("| 检索关键词 | 公司/主题 | 行业/标签 | 日期 | 卡片路径 | 关联报告 |\n")
            f.write("|:---|:---|:---|:---|:---|:---|\n")
            f.write("\n## 二、行业/主题研究\n\n")
            f.write("| 检索关键词 | 主题名称 | 行业/标签 | 日期 | 卡片路径 | 关联报告 |\n")
            f.write("|:---|:---|:---|:---|:---|:---|\n")
            f.write("\n## 三、宏观/市场事件\n\n")
            f.write("| 检索关键词 | 事件名称 | 标签 | 日期 | 卡片路径 | 关联报告 |\n")
            f.write("|:---|:---|:---|:---|:---|:---|\n")

    # 在对应 section 的表格末尾追加
    with open(KB_INDEX, "r", encoding="utf-8") as f:
        lines = f.readlines()

    section_header = f"## {section}"
    insert_idx = None
    in_section = False
    for i, line in enumerate(lines):
        if section_header in line:
            in_section = True
        if in_section and line.startswith("## ") and section_header not in line:
            insert_idx = i  # 下一个 ## 之前插入
            break

    if insert_idx is not None:
        lines.insert(insert_idx, new_row)
    else:
        lines.append(new_row)  # 追加到末尾

    # 更新日期
    updated_lines = []
    for line in lines:
        if line.startswith("**最后更新**"):
            updated_lines.append(f"**最后更新**: {today_str}\n")
        else:
            updated_lines.append(line)

    # Atomic write: write to temp file then rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=KB_DIR, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        os.replace(tmp_path, KB_INDEX)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.info("KB_INDEX.md updated (%s)", section)


def _update_index(filename, title, tags, card_type):
    """保留旧函数（兼容性），写入 README.md（已弃用，仅备份用）"""
    entry = f"- [{title}](./{filename}) | {tags} | {card_type} | {datetime.now().strftime('%Y-%m-%d')}\n"
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            f.write("# Knowledge Base Index\n\n")
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.info("README index updated (legacy)")


def _sync_to_obsidian(filepath, filename):
    """同步知识卡片到 Obsidian vault"""
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path:
        return

    target_dir = os.path.join(vault_path, "Knowledge_Base")
    os.makedirs(target_dir, exist_ok=True)

    target_path = os.path.join(target_dir, filename)
    try:
        import shutil
        shutil.copy2(filepath, target_path)
        logger.info("Synced to Obsidian: %s", target_path)
    except Exception as e:
        logger.warning("Obsidian sync failed: %s", e)


def sync_reports_to_obsidian():
    """批量同步报告到 Obsidian vault"""
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path:
        logger.warning("OBSIDIAN_VAULT_PATH not configured")
        return

    import shutil
    reports_dir = os.path.join(PROJECT_ROOT, "Reports")

    for root, dirs, files in os.walk(reports_dir):
        for f in files:
            if f.endswith(".md"):
                src = os.path.join(root, f)
                relative = os.path.relpath(src, reports_dir)
                dst = os.path.join(vault_path, "Reports", relative)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

    logger.info("Reports synced to Obsidian: %s", vault_path)
