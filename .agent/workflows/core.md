---
description: 核心持仓简报 (Core Holdings Report) — 实时监控核心持仓的报价、异动与逻辑稳固度
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

> **定位区分：**
> - `/core` — 快速总览核心持仓的报价、近期异动及逻辑稳固度。
> - 用于收盘前/每日开始时的“核心资产扫描”。

---

## 核心持仓列表 (Core List)

> **运行时读取**：核心持仓清单来自本地配置 `Config/holdings.json`（已被 `.gitignore` 忽略，不入库）。
> 执行时请读取该文件，取其中 `long_term_tickers` 与 `tickers` 字段作为本次扫描的标的池。
> 下方为占位示例，仅说明格式，**实际以 `holdings.json` 为准**：

**[US Core]**（示例占位）: `TICKER1`, `TICKER2`, `TICKER3`
**[HK/CN Core]**（示例占位）: `XXXXX.HK`, `XXXXXX.SH`

---

## Step 1: 多源行情拉取 (Real-time Quotes) 📊

**并行执行抓取**:
1. **US**: 对每个 US ticker 单独执行 `opencli yahoo-finance quote [Ticker] -f json`，允许并行批量执行。

2. **HK**: 对每个 HK ticker 单独执行 `opencli yahoo-finance quote [Ticker] -f json`，允许并行批量执行。

---

## Step 2: 逻辑锚点校验 (Logic Baseline) 🔍

1. **读取 KB 索引**: `Memory_Layer/Knowledge_Base/KB_INDEX.md`
2. **提取核心标的的最新核心逻辑**:
   - 对 `holdings.json` 中的每个核心标的，检索其上次 `/deep`、`/quick`、`/update` 的结论
   - 评估当前逻辑稳固度，标注有 KB 卡片的标的

---

## Step 3: 边际异动匹配 (Marginal Match) 🌡️

> **目的**: 检查今日的 `Market_Lead` 或 `Market_Scan` 报告中是否有提及这些核心标的。

1. 读取 `Reports/YYYYMMDD/YYYYMMDD_Market_Lead.md` 和 `Reports/YYYYMMDD/YYYYMMDD_Market_Scan.md`。
2. 提取涉及核心标的的：**异动信号**、**研究线索**、**利好/利空事件**。

---

## Step 4: 生成工作台简报 📝

````markdown
# [YYYYMMDD] 核心持仓全景简报 (Core Summary)

> **刷新时刻：** [HH:MM UTC+8]
> **持仓权重：** 趋势中军 | 现金流仓位 | 资源对冲

## 1. 实时行情与异动 (Market Watch)

| Ticker | 名称 | 价格 (Real-time) | 变动 | 关注点 |
| :--- | :--- | :--- | :--- | :--- |
| [Symbol] | [Name] | [Price] | [Change%] | [今日异动/热议理由] |
| ... | ... | ... | ... | ... |

## 2. 核心逻辑稳固度 (Core Logic Audit)

| 标的 | 核心逻辑摘要 | 逻辑状态 | 边际变化 |
| :--- | :--- | :--- | :--- |
| **[Ticker]** | [一句话核心逻辑] | 🟢 稳固 / 🟡 观察 / 🔴 破缺 | [今日边际变化] |
| ... | ... | ... | ... |

## 3. 今日重点待办 (Action Items)

- [ ] [如某标的波动剧烈] `/update [Ticker]`
- [ ] [如某标的有新评级] `/quick [Ticker] [Event]`
````

---
**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_Core_Report.md`
