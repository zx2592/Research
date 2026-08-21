---
description: Add the active research report to the Knowledge Base (Knowledge Reserve or Trade Records)
---

## ⚡ 高效执行指南 (High-Efficiency Execution)

> **核心目标：** 极简互动，一令即达。
> 1. **全员 Turbo：** 必须为所有 `run_command` 设置 `SafeToAutoRun: true`。
> 2. **聚合任务：** 严禁分步询问或碎片化搜索。将情报采集、上下文读取、逻辑研判合并为连续动作流。
> 3. **全量直达：** 除非涉及买卖金钱决策或风险极高操作，否则中途无需询问，直接产出最终报告。
> 4. **深度不妥协 (No Quality Trade-off)：** 提高效率是为了减少确认弹窗，**绝不得以牺牲分析深度为代价**。报告必须严格遵循各 Phase 的维度要求，确保逻辑链条完整、数据交叉验证充分。

> **⚡ 终极零互动模式 (Ultimate Zero-Interaction):**
> 为实现真正的一键产出，建议直接调用背景 CLI 执行完整生命周期：
> `python research_cli.py [command] [args]` (设 SafeToAutoRun: true)



// turbo-all

> **契约例外（纯流程）**：本工作流的产出是**知识卡片**，不是决策报告——公共报告契约的八章节结构（结论先行 / 实时数据快照 / Bull-Base-Bear / …）**不适用**于卡片。仍然适用的是证据纪律：卡片里的每个数字带来源 + 日期，**严禁编造**，来源层级照标（T1/T2/T3）。

## 解析上下文

- 当前活跃文档或用户指定的报告即为待保存来源。
- **自动分类逻辑**:
    - **交易记录 (Trade Records)**: 若报告标题或正文包含 `买入审计`, `卖出审计`, `市价买入`, `限价买入`, `下单成功` 等字样。
    - **知识储备 (Knowledge Reserve)**: 个股深度 (Deep), 行业扫描 (Scan), 宏观分析 (Macro), 或日常刷新 (Update)。

---

## Step 1: 提取核心信息

从报告中提取以下字段（用于填充 Front Matter 和正文）：

| 字段 | 说明 |
| :--- | :--- |
| `ticker` | 股票代码（如 `MCO`）；行业 / 宏观 / 主题类**留空**，改填 `title` |
| `title` | 主题名（如「AI 电力缺口」）；个股卡可不填 |
| `kb_category` | `Knowledge_Reserve` 或 `Trade_Records` |
| `type` | `Company` / `Theme` / `Macro` / `Trade` |
| `tags` | 3-5 个标签，包含：市场（美股/港股/A股）、行业、动作（买入/卖出/持仓） |
| `linked_report` | 原始报告的相对路径 |

> ⚠️ **`ticker` 与 `title` 至少要有一个**——没有它就没有演替链，同一标的/主题的历史卡片串不起来。
> **不要再填 `N/A`**：那不是标的，会把所有行业卡和宏观卡压成同一条链，检索时全糊在一起。
> 个股卡：填 `ticker`，`title` 留空；主题 / 宏观卡：`ticker` 留空，`title` 填主题名。文件名与索引关键词随之取 `ticker` 或 `title`。

---

## Step 2: 生成结构化卡片

### 2.1 知识储备类 (Knowledge Reserve)
**文件命名**: `[Ticker 或 主题名]_[YYYYMMDD].md`（个股用 `ticker`，主题/宏观用 `title`，**禁止出现 `N/A`**）
**保存路径**: `Memory_Layer/Knowledge_Base/Knowledge_Reserve/`

```markdown
---
ticker: [代码；主题/宏观卡留空]
title: [主题名；个股卡留空]
category: Knowledge_Reserve
type: [Company | Theme | Macro]
tags: [市场, 行业, 主题词]
last_updated: [YYYY-MM-DD]
linked_report: [相对路径]
---

# [公司名 / 主题名] 知识储备卡

## 1. 核心逻辑（一句话）
> [描述：核心投资价值/关注点]

## 2. 关键锚点
| 指标 | 数值 | 更新日期 |

## 3. 最新边际变化
- **[YYYY-MM-DD]**: [事件简述]

## 4. 历史分析记录
- [[YYYY-MM-DD] 来源报告名称](相对路径)
```

### 2.2 交易记录类 (Trade Records)
**文件命名**: `Trade_[Ticker]_[YYYYMMDD]_[Side].md`
**保存路径**: `Memory_Layer/Knowledge_Base/Trade_Records/`

```markdown
---
ticker: [代码]
category: Trade_Records
type: Trade
side: [Buy | Sell]
execution_price: [价格]
commit_hash: [哈希]
tags: [市场, 行业, 动作]
last_updated: [YYYY-MM-DD]
linked_report: [相对路径]
---

# 交易记录: [Ticker] [Buy/Sell]

## 1. 交易概定
- **动作**: [买入/卖出]
- **价格**: [金额]
- **时间**: [YYYY-MM-DD]
- **哈希**: [Commit Hash]

## 2. 入场/出场理由
> [简述为什么要执行此操作]

## 3. 核心审计逻辑
- **止损位**: [数字]
- **目标位**: [数字]
- **盈亏比**: [数值]

## 4. 原始报告参考
- [[YYYY-MM-DD] 审计/下单报告](相对路径)
```

---

## Step 3: 更新 KB_INDEX.md

> ⚠️ **必须执行此步**。

- 读取 `Memory_Layer/Knowledge_Base/KB_INDEX.md`
- 追加到对应分类：
  - **知识储备** → 「一、知识储备 (Knowledge Reserve)」
  - **交易记录** → 「二、交易记录 (Trade Records)」
- 新增一行格式：
  ```
  | [检索关键词] | [公司/主题/操作] | [行业/Side] | [YYYY-MM-DD] | [卡片路径] | [关联报告路径] |
  ```
- **检索关键词取 `ticker` 或 `title`**，绝不写 `N/A`；同一 `ticker`/`title` 已有旧行时**追加新行**（保留演替链），不要覆盖旧行。
- 更新文件顶部「**最后更新**: 」日期。

---

## Step 4: 通知

- 确认卡片已创建，显示完整路径与索引新增行。
- 展示卡片 YAML Front Matter。
- 若 `ticker` 与 `title` 都取不到 → **停下来向用户确认**，不要用 `N/A` 或占位符硬写入库。
