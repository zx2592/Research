---
description: 事件驱动快速评论 — 公司边际变化、突发事件的快速定性与策略推演
---

// turbo-all

## ⚡ 高效执行指南 (High-Efficiency Execution)

> **核心目标：** 闪电快评，零交互产出。
> 1. **全员 Turbo：** 必须为所有 `run_command` 设置 `SafeToAutoRun: true`。
> 2. **一次性情报捕获：** 严禁分步搜索。将「事件详情、市场反应、分析师点评」合并为 1 次深度聚合查询。
> 3. **全量直达：** 获取知识库基准、采集增量、研判定性、生成报告，应一气呵成。中途不应中断询问。
> 4. **深度不妥协 (No Quality Trade-off)：** 提高效率是为了减少确认弹窗，**绝不得以牺牲分析深度为代价**。报告必须严格遵循各 Phase 的维度要求，确保逻辑链条完整、数据交叉验证充分。

> **⚡ 终极零互动模式 (Ultimate Zero-Interaction):**
> 为实现真正的一键产出，建议直接调用背景 CLI 执行完整生命周期：
> `python research_cli.py [command] [args]` (设 SafeToAutoRun: true)

> 4. **静默背景处理：** 对事件本质的判断、Priced-in 分析应快速在推理中完成，直接输出结论。

## Quick Event Workflow

This workflow automates the generation of a "Quick Event Comment" (事件快评) using the `quick_event.py` script.

### Usage
- `/quick [Ticker] [Event Description]`

### Steps
1.  **Execute Script**:
    - Runs `python scripts/quick_event.py [Ticker] [Event]`
    - Automatically fetches market data, news, and analyst views.
    - Generates a markdown report in `Reports/YYYYMMDD/`.
    - Syncs to Obsidian.

### Example
- `/quick NVDA "Earnings Beat"`
- `/quick TSLA "Recall News"`

### Output
- A generated markdown file: `YYYYMMDD_[Ticker]_Quick.md` containing:
    - Event Summary (Class A/B)
    - 3-Step Analysis (What, Why, Impact)
    - Investment & Strategy Deduction
    - Knowledge Base Update Summary

// turbo
python scripts/quick_event.py {args}

---

## Step 0: 知识库预检 🔍

> **目的**: 在消耗搜索配额之前，先命中索引，实现「站在过去工作的肩膀上」。

**查询步骤**（按顺序，命中即停）：

**① 查 KB 索引**（首选，秒级完成）
- 读取 `Memory_Layer/Knowledge_Base/KB_INDEX.md`
- 在「检索关键词」列搜索：`[Ticker]` / `[公司中文名]` / `[行业关键词]`
- **命中** → 按「卡片路径」列读取对应 `.md` 文件；若「关联报告路径」非空，一并读取 → 跳到「命中处理」
- **未命中** → 执行②

**② 扫描近期日报**（补充，仅在①未命中时执行）
- 扫描 `Reports/` 各日期子目录（最近 90 天），搜索包含 `[Ticker]` 的文件名
- **命中** → 读取最新一份报告的结论段落 → 跳到「命中处理」
- **未命中** → 标注「🆕 首次分析」，直接执行 Step 1+（全量搜索）

**命中处理**：
- 提炼「已知核心逻辑 + 最近边际变化 + 已识别风险」
- 在报告顶部标注「📚 基于历史档案（来源：[文件名]）」
- 分析时重点聚焦**增量变化**，跳过已知背景，节省搜索配额

---

## Step 1: 事件定性与噪音过滤

### 1.1 信息分级
判断该事件属于哪一级别：

| 级别 | 定义 | 对长线权重 | 对短线权重 |
| :--- | :--- | :--- | :--- |
| **Class A** | 财报 / 官方公告 / 实质性数据 | 高 | 高 |
| **Class B** | 传闻 / 情绪 / 观点 / 大V推荐 | 低 | 高 |

### 1.2 事件本质判断
- **Fact Check**: 事件改变了「长线基本面逻辑」，还是只提供了「短期情绪燃料」？
- **Priced-in Analysis**:
  - 利好不涨 / 利空不跌 → 预期已透支 / 利空出尽
  - 走势与消息一致 → 趋势加强
- **逻辑验证**: 事件对核心投资逻辑是 **增强** / **削弱** / **无关**？

**搜索动作**:
- `[Company] [Event] impact`
- `[Company] [Event] analyst reaction`

---

## Step 2: 边际变化分析

### 2.1 What — 发生了什么
- 1-2 句话客观陈述事件

### 2.2 Why — 为什么重要
- 这件事在公司发展脉络中的位置
- 对商业模式 / 竞争格局 / 财务的边际影响

### 2.3 Impact — 影响多大
- 对 EPS / Revenue / Margin 的具体影响估算（如有数据）
- 对估值（PE / 市值）的传导逻辑

---

## Step 3: 局势与投资推演

### 3.1 核心玩家扫描
- 扫描事件波及的核心玩家：上市标的（标明 Ticker）+ 关键人物/未上市巨头
- **定性**: 谁是赢家（护城河加深）？谁是输家（逻辑被颠覆）？谁在焦虑？

### 3.2 投资逻辑推演
- **长线视角**: 产业链哪个环节业绩最确定？（卖铲子的人）
- **短线视角**: 短期情绪是否过热？是否存在认知预期差？
- 提供「观察指标」和「逻辑验证点」

---

## Step 4: 双轨策略推演

### 长线护城河视角
- **核心逻辑检验**: 护城河或长期造血能力是否发生结构性变化？
- **估值/赔率**: 如果是坏消息，跌出了"黄金坑"吗？如果是好消息，变成"追高"了吗？
- ⚠️ 警惕：在上涨幻觉中加仓

### 短线势能视角
- **势能检验**: 势能还在吗？技术面是否破位？传播势能是否衰竭？
- **情绪检验**: 当前是 FOMO 还是恐慌？
- ⚠️ 警惕：交易转持有（被套后不止损）

---

## 输出报告

```markdown
# [YYYYMMDD] [Ticker] 事件快评

> **事件：** [一句话描述]
> **信息级别：** Class A / Class B
> **核心判断：** Bullish / Bearish / Neutral
> **逻辑影响：** 增强 / 削弱 / 无关

## 1. What — 发生了什么
...

## 2. Why — 为什么重要
...

## 3. Impact — 边际影响
- EPS 影响: ...
- 估值传导: ...
- 目标价影响: [无变化 / 上调 / 承压]

## 4. 局势与投资推演

### 核心玩家
| 角色 | 标的 | 定性 |
| :--- | :--- | :--- |
| 赢家 | ... | 护城河加深 |
| 输家 | ... | 逻辑被颠覆 |

### 投资推演
- 长线确定性环节: ...
- 短线情绪/预期差: ...
- 观察指标: ...

## 5. 策略推演

### 长线护城河
- 逻辑: [稳固 / 需重估]
- 建议: ...

### 短线势能
- 势能: [延续 / 衰竭 / 反转]
- 建议: ...

## 6. 知识库更新摘要
> [需追加到个股档案的关键点]

---
**生成模型**: [IDE Agent] (Gemini 2.5 Flash)
```

**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_[Ticker]_Quick.md`

---

## 保存与通知

1. 用 `write_to_file` 保存报告
2. 在最终回答中展示完整快评（快评本身就短），询问是否 `/add` 保存到知识库
