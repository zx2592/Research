---
description: 核心持仓简报 (Core Holdings Report) — 实时监控核心持仓的报价、异动与逻辑稳固度
---

// turbo-all

> **契约**：本工作流的报告必须遵守注入在本文件之前的三份公共契约（`common/00-report-contract.md` 报告结构 / `common/10-evidence-contract.md` 证据标准 / `common/20-quality-gate.md` 质量门禁）。组合级简报的「证据台账」按**每个核心标的一行的逻辑稳固度审计**来落。

## ⚡ 高效执行指南 (High-Efficiency Execution)

> **核心目标：** 极简互动，一令即达。
> 1. **全员 Turbo：** 必须为所有 `run_command` 设置 `SafeToAutoRun: true`。
> 2. **聚合任务：** 严禁分步询问或碎片化搜索。将情报采集、上下文读取、逻辑研判合并为连续动作流。
> 3. **全量直达：** 除非涉及买卖金钱决策或风险极高操作，否则中途无需询问，直接产出最终报告。
> 4. **深度不妥协 (No Quality Trade-off)：** 提高效率是为了减少确认弹窗，**绝不得以牺牲分析深度为代价**。报告必须严格遵循各 Phase 的维度要求，确保逻辑链条完整、数据交叉验证充分。

> **⚡ 终极零互动模式 (Ultimate Zero-Interaction):**
> 为实现真正的一键产出，建议直接调用背景 CLI 执行完整生命周期：
> `python research_cli.py [command] [args]` (设 SafeToAutoRun: true)

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
3. **兜底与取证**：`opencli` 不可用或返回异常时改用 `get_realtime_quote(ticker)`。
4. **逐个记录抓取时间**：价格、涨跌幅、来源、`fetched_at` 一并落进证据台账——「我什么时候知道的」和「数是多少」同样重要。

> 只有当某个标的**要给动作价/止损/目标价**时才需要 `cross_validate_price(ticker)`；简报默认单源，如实在价格证据行申报即可。

---

## Step 2: 逻辑锚点校验 (Logic Baseline) 🔍

1. **读取 KB 索引**: `Memory_Layer/Knowledge_Base/KB_INDEX.md`
2. **提取核心标的的最新核心逻辑**:
   - 对 `holdings.json` 中的每个核心标的，检索其上次 `/deep`、`/quick`、`/update` 的结论作为**基线**
   - 每条基线必须标注**来源文件 + 结论日期 + 层级**（自有历史报告按 T2 计）
   - 评估当前逻辑稳固度，标注有 KB 卡片的标的
3. **KB 过期识别**：基线日期距今 > 60 天，或该标的近期无任何新证据 → 记入「证据缺口」

---

## Step 3: 边际异动匹配 (Marginal Match) 🌡️

> **目的**: 检查今日的 `Market_Lead` 或 `Market_Scan` 报告中是否有提及这些核心标的。

1. 读取 `Reports/YYYYMMDD/YYYYMMDD_Market_Lead.md` 和 `Reports/YYYYMMDD/YYYYMMDD_Market_Scan.md`。
2. 提取涉及核心标的的：**异动信号**、**研究线索**、**利好/利空事件**，逐条带来源 + 时间。
3. **当日复用**：这两份报告今天已经跑过的，直接引用其结论（带原时间戳），把搜索预算留给未覆盖的标的。

---

## Step 4: 生成工作台简报 📝

> 按公共报告契约的章节组织，组合级简报把「逐标的审计」落在证据台账里。

````markdown
# [YYYYMMDD HH:MM] 核心持仓全景简报 (Core Summary)

## 结论先行
- **一行判决**：`整体评级[强多/多/中性/空/强空] · 动作[减/持/加/观察] · 置信度[高/中/低] · 一句理由(≤30字)`
- **今日最需动作的 1-2 个标的**：`[Ticker] → [动作] · [触发它的那条证据]`
- **相对上次**：[变化 / 无变化 / 🆕首次]
- **价格证据**：[按公共契约二选一如实写；简报默认单源时写「单源未交叉」，并不得给目标价/止损/盈亏比]

## 实时数据快照

| Ticker | 名称 | 价格 | 变动% | 来源 | 抓取时间 | 交叉验证 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [Symbol] | [Name] | [Price] | [Change%] | opencli/get_realtime_quote | [HH:MM UTC] | 是/否/未做 |

## 证据台账（= 逐标的逻辑稳固度审计）

| 标的 | 核心逻辑摘要 | 逻辑状态 | 边际变化 | 来源 | 时间 | 层级 | 对结论的影响 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **[Ticker]** | [一句话核心逻辑] | 🟢 稳固 / 🟡 松动 / 🔴 恶化 | [今日边际变化] | [文件/链接] | [日期] | T1/T2/T3 | [增强/削弱/无关] |

> **必含一行反方**：今日**最该警惕的标的**及其恶化证据。

## Bull/Base/Bear（组合层面）

| 情景 | 概率 | 关键假设 | 对组合含义 | 触发条件 |
| :--- | :--- | :--- | :--- | :--- |
| Bull | | | | |
| Base | | | | |
| Bear | | | | |

## 行动计划

- [ ] [波动剧烈] `/update [Ticker]` — 触发条件：[…]
- [ ] [有新事件] `/quick [Ticker] [Event]` — 触发条件：[…]
- **看错信号**：[出现什么 = 本简报的整体判断作废]
- **下次复盘点**：[日期 / 事件]

## 风险与不确定性

[数据延迟、假设、未覆盖的标的]

### 证据缺口

- [缺什么] — [影响哪个判断] — [下一步去哪取]
- [KB 基线已过期的标的] — [逻辑状态无法确认] — `/update [Ticker]`

## 质量自检

- `check_report_quality(markdown)` 结果：[passed]
- ✅ 质量Gate 8/8（或 ⚠️ N/8，未过项见上）
````

---

## 保存与通知

1. 先 `check_report_quality(markdown)`，通过后再 `write_to_file` 保存到 `Reports/YYYYMMDD/YYYYMMDD_Core_Report.md`（落盘是必须动作，严禁只回复不保存）。
2. 在最终回答中展示：整体判决 + 今日最需动作的标的 + 逻辑状态变化的标的。
