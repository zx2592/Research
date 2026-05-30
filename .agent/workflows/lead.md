---
description: 市场领航者 (Market Lead) — 穿越雪球、Reddit 与专业研报的全球情绪共振审计
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


## 解析参数

- `/lead [Optional Keyword]`（如 `/lead 智驾` 或直接 `/lead` 扫描全场）

---

## Step 1: 多源情报同步 (opencli) 📡

> **目的**: 利用已登录的社交态，抓取最真实的一手讨论，避免滞后的新闻稿。

**并行执行以下抓取动作（30-60s）**:

1. **雪球全场扫描**:
   - `opencli xueqiu hot-stock --limit 10 -f json` (捕捉人气焦点)
   - `opencli xueqiu feed --limit 20 -f json` (捕捉实时讨论流)
   - `opencli xueqiu hot --limit 10 -f json` (捕捉高赞逻辑)

2. **Reddit 全球共振**:
   - **高风险/散户**: `r/WallStreetBets`, `r/amcstock`, `r/pennystocks`
   - **研究/价值**: `r/stocks`, `r/investing`, `r/ValueInvesting`
   - *执行*: `opencli reddit subreddit [Subreddit] --sort hot --limit 10 -f json`

3. **Twitter/X KOL 追踪**:
   - 读取 `Config/我的关联偏好.md` 中的 `🎙️ KOL 监控` 列表。
   - 对列表中的每个 Twitter KOL 执行：`opencli twitter search "from:[Handle]" --filter live --limit 5 -f json` (重点追踪 `labubu_trader`)

---

## Step 3: 全场逻辑发现 (Discovery First) 🧠

> **目的**: 将数千字的社交数据和研报数据转化为结构化线索，优先处理外部信号。

**LLM 处理逻辑**:
1. **全景扫描**: 优先处理来自雪球、Reddit 和 Twitter/X KOL 的全场热门数据，提取 **Ticker**、**核心论点**、**逻辑支撑点**。
2. **去重与降噪**: 过滤情绪垃圾，识别提及频率高且逻辑扎实的新议题。

---

## Step 4: 自选股异动对撞 (Watchlist Correlation) 🔍

> **目的**: 在完成全场发现后，检查自选股中是否有同样值得关注的异动。

1. 读取 `Config/我的持仓.md` 和 `Config/我的关联偏好.md`。
2. 对持仓/自选标的在社交媒体上的热度进行专项匹配，作为补充线索。

---

## Step 5: 十大核心线索审计 (60% Discovery Rule) ⚖️

> **目的**: 按照"靠谱程度"对线索进行排名，强制防止过度拟合。

**评判标准**:
- **发现占比 (New Clues)**: **Top 10 线索中必须包含 ≥ 60%（即 6 条及以上）的不在持仓/关联偏好列表中的"新发现"**，以确保探索广度。 (权重 25%)
- **事实密度**: 是否包含具体的财报数据、行业政策、供应链细节？ (权重 25%)
- **博弈价值**: 该讨论是否反映了市场尚未完全定价 (Unexpected) 的变化？ (权重 20%)
- **全局一致性**: 是否在雪球和 Reddit 同时出现某种"共振"？ (权重 15%)
- **研报背书**: 该线索是否有券商研报支撑？有 = 置信度加分。 (权重 15%)

**线索来源标注**: 每条线索必须标注其原始来源（雪球/Reddit/Twitter/搜索引擎），格式: `[来源: xxx]`

---

## Step 6: 报告生成与存储 📂

1. **生成 Markdown 报告**: `Reports/YYYYMMDD/YYYYMMDD_Market_Lead.md`
2. **归档**: 使用 `write_to_file`。

---

## Step 7: 主动汇报 📢

- 在最终回答中向用户展示最震撼的 3 条核心线索。
- 引导用户进行追问或深度研究：

```
💡 对以上线索感兴趣？你可以：
  - 回复"展开第N条"或输入 Ticker 进行追问深挖
  - 回复 "/deep [Ticker]" 对潜力线索进行完整财务底稿审计
```

---

## Step 8: 追问深挖 (Drill-Down on Follow-up) 🔍

> **目的**: 当用户对某条线索追问时，回到信息来源网站进行定向搜集，提供更深层次的信息。

**触发条件**: 用户回复追问（如"展开说说第3条"、"NVDA 的研报具体说了什么"、"这个标的雪球上怎么讨论的"）

**执行流程**:

1. **识别线索来源**: 从 Top 10 中定位该线索，确认其原始来源标注（雪球/Reddit/Twitter/搜索引擎）。

2. **定向深挖**: 根据来源调用 `drill_source(source, query)`：
   - `source="xueqiu"` → 回到雪球搜索该标的的最新讨论、大V观点
   - `source="reddit"` → 回到 Reddit 搜索该标的的深度帖子
   - `source="web"` → 通用网页搜索该标的的最新新闻和分析

3. **补充验证**: 用 `search_web` 补充搜索该标的的最新财报数据、分析师评级变动、近期事件。

4. **结构化回复**: 以"追问答复"格式返回：
   ```markdown
   ## 🔍 追问深挖: [标的/话题]

   ### 来源回溯 ([来源网站])
   - [从来源网站获取的详细讨论/研报内容]

   ### 补充验证
   - [最新新闻/财报/评级变动]

   ### 风险提示
   - [该线索的主要风险点]

   ---
   💡 需要完整财务审计？回复 "/deep [Ticker]"
   ```

---

## 报告模板示例

```markdown
# [YYYYMMDD] 全球市场领航者报告

> **市场气温：** [🌡️ 极热 / 🌤️ 均衡 / ❄️ 冰封]
> **线索分布：** 🆕 新发现 [N]% | 📌 关联自选 [M]%
> **数据源：** 雪球 ✅ | Reddit ✅ | Twitter ✅

## 🌟 十大核心研究线索 (Top logic)

1. **[逻辑标题]** (标的: [Ticker]) [来源: 雪球/Reddit/Twitter]
   - 核心论点: ...
...
```
