---
description: Analyze a company using the "Quality Compounder" framework (Buffett/Li Lu/Duan Yongping/Darwin).
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

> **契约**：本工作流的报告必须遵守注入在本文件之前的三份公共契约（报告结构 / 证据标准 / 质量门禁）。**财务与估值数字必须 ≥2 个独立来源交叉，并回溯到 T2 一手披露**（10-K / 年报 / IR）；复利分析要 5-10 年纵深，凭印象的长期数据一律不许写进结论。
> **⚠️ 模型要求**：用最高智力档模型执行。

1.  **Parse Arguments**:
    - Command: `/value [Ticker]` (e.g., `/value BRK.B` or `/value AAPL`)

1.5. **Step 0: 知识库预检 🔍**

    > **目的**: 复利分析需要 5-10 年数据，建档成本高。先命中索引，复用已有财务基线，避免重复收集。

    **查询步骤**（按顺序，命中即停）：

    **① 查 KB 索引**（首选，秒级完成）
    - 读取 `Memory_Layer/Knowledge_Base/KB_INDEX.md`
    - 在「检索关键词」列搜索：`[Ticker]` / `[公司中文名]`
    - **命中** → 读取知识卡片；若「关联报告路径」指向 deepdive，一并读取财务数据表 → 跳到「命中处理」
    - **未命中** → 执行②

    **② 扫描 deepdive 目录**（补充）
    - 扫描 `Reports/deepdive/` 查找含 `[Ticker]` 的 Value/Deep 报告
    - **命中** → 跳到「命中处理」
    - **未命中** → 标注「🆕 首次质量评估」，执行完整 5-10 年数据收集

    **命中处理**：
    - 读取前一份档案的 Key Financials 表、护城河结论、估值锚点作为基准
    - 本次重点更新：最新年度数据 + 护城河侵蚀核查 + 估值刷新
    - 查询 `Memory_Layer/Investment_Persona.md` 了解投资风格偏好
    - 报告标注「📚 基于 [日期] 档案更新（来源：[文件名]）」


    - **Objective**: Identify "Consistency" and "Resilience".
    - > **⚠️ 模型要求**: 请务必使用 **gemini-3.1-pro-preview** 或同等级别最高智力模型执行此 Workflow。
    - **Agentic Search**:
        - **Financials**: 10-year Revenue CAGR, ROIC/ROCE trends, Gross Margin stability, FCF Conversion.
        - **Capital Allocation**: Share buyback history (share count reduction), Dividend growth history.
        - **Constraint**: Use **Calendar Year (CY)** where possible to ensure comparability（财年需标注映射，如 CY2026 ≈ FY27）。
    - **取数顺序（守证据契约）**：A股先调 `get_financials(ticker)` 拿结构化年报；其余市场先用 `browser_fetch` / `drill_source` 打开 10-K / 年报 / IR 页面拿底稿，再用 `search_web` 补第二源与定性材料。**结构化不等于已交叉**——≥2 个**独立族**来源仍是硬要求，取到后用 `cross_validate_metric` 算误差（≤1% / 1-5% / >5% 三档）；两源不一致时并列写出并说明取舍。
    - **复权口径**：10 年 CAGR、历史 PE 分位、历史 EPS 一律用**前复权**，同一份报告内不得混用；当前市值/PE 用当前股价×当前总股本，并用 `verify_market_cap` 验算股本口径。
    - **联网取证一律走本项目工具**（`search_web` / `browser_fetch` / `drill_source` / `learn_source`），否则证据台账事后无从回溯。
    - **价格取证**：`get_realtime_quote(ticker)` 取现价；**要给目标价或安全边际价时必须 `cross_validate_price(ticker)`**，结果写进结论区的价格证据行；单源未交叉则不给目标价与安全边际价。

3.  **Mental Model Application (The "Masters" Framework)**:
    - **Warren Buffett**:
        - *Moat*: Is it widening? (Brand, Switching Cost, Network Effect).
        - *Simple*: Is the business easy to understand?
    - **Li Lu (Modern Value)**:
        - *Growth as Value*: Is it a "long slope, heavy snow" business?
        - *Circle of Competence*: Is the business evolving or being disrupted?
    - **Duan Yongping (Benfen)**:
        - *Culture*: Does management do the "right thing"? (Honest guidance, shareholder alignment).
        - *Stop Doing Wrong*: Any history of bad acquisitions or fraud?
    - **Darwin (Evolution)**:
        - *Adaptability*: How did it survive the last crisis (e.g., 2020, 2022)?
        - *Niche*: Is it the "Apex Predator" in its specific ecosystem?

3.5. **多哲学对撞 (6-Philosophy Confrontation)**:

    > 在 4 位质量大师之外，再用 6 种**截然不同的世界观**审视同一份数据，让结论从碰撞中浮现——破"质量滤镜"单一视角偏误。每种表态 **做多 / 做空 / 弃权**，给 1-2 句核心理由 + 最大风险；若弃权，注明哪种风格可能有不同看法。

    | 视角 | 代表 | 核心问题 | 周期 | 关键指标 |
    | :--- | :--- | :--- | :--- | :--- |
    | 质量复利 | 巴菲特/芒格 | 20 年后它更强吗？ | 永久 | ROIC 趋势 |
    | 想象力成长 | Baillie Gifford/ARK | 一切顺利时上限多大？ | 5 年+ | 营收增速 |
    | 基本面多空 | Tiger Cubs | 市场漏看了什么？预期差？ | 1-3 年 | EV/EBITDA |
    | 深度价值 | Klarman/Marks | 私人买家愿为整间公司付多少？ | 耐心等待 | 重置成本 |
    | 催化剂驱动 | Tepper/Ackman | 什么具体事件触发重定价？ | 6-18 月 | 催化时间表 |
    | 宏观择时 | Druckenmiller | 当前流动性环境意味着什么？ | 随周期 | Fed 政策 |

    > **对撞结论**：统计 6 票中 多/空/弃权 分布。一致看多 = 强信号；多空分裂 = 预期差所在，须在估值锚点中说明你站哪边、为什么。

4.  **Synthesize Report (Quality Verdict)**:
    - **Format**: Based on `Workflow_Layer/Templates/Template_A_Quality_Compounder.md`.
    - **CRITICAL: The Report MUST be written in CHINESE (Simplified).**
    - **Sections**（按公共报告契约的章节组织，专业模块嵌在其中）：
        - **结论先行**：`Quality Score[如 A+ Compounder] · 评级 · 动作[买/等/继续研究] · 置信度[高/中/低] · 一句理由(≤30字)` + 相对上次档案的变化（无历史标「🆕首次质量评估」）+ **价格证据行**。
        - **实时数据快照**：现价 / 涨跌幅 / 市值 / 52周区间，带来源、抓取时间、交叉验证结果。
        - **证据台账**：护城河 / 资本配置 / 管理层 / 达尔文 四维关键判断逐条带证据、来源、时间、层级（T1/T2/T3），**必含一行反方 (Bear)**。
        - **关键变化**：vs 上次档案（护城河 / 财务基线 / 估值 / 各维得分，⬆️⬇️↔️）。
        - **数字底稿 (Key Financials)**：TTM + 5yr/10yr CAGR、ROIC/ROCE、毛利率、FCF 转化、Forward PE (CY26/CY27)、PEG、历史 PE 区间与当前分位——**每个数字带时间 + 来源层级**。
        - **Bull/Base/Bear**：三情景 + 概率（合计 100%）+ 12M 目标价 + 触发条件。
        - **行动计划**：可执行（仓位 % / 价格区间 / 时间窗）+ 买点 / 加仓 / 卖出 / 复盘触发器 + **看错信号** + 下次复盘点。
        - **风险与不确定性**（含 `### 证据缺口`：`[缺什么] — [影响哪个判断] — [下一步去哪取]`）。
        - **质量自检**：`check_report_quality` 结果 + 印章 `✅ 质量Gate 8/8`。
        - **0. Key Financials**: Table with TTM and 5yr CAGR.
        - **0.5 质量记分卡 (Quality Scorecard)**: 见下方加权评分表；最终质量等级（A+/B-...）须由此复合分推导，而非凭感觉。
        - **1. Darwinian Analysis**: Ecosystem position and survival trait.
        - **2. The "Moat" Assessment**: Strong/Stable/Eroding.
        - **3. Management & Culture (Benfen)**: Integrity check.
        - **4. Valuation Anchor**: Is it a "Great Company at a Fair Price"?
        - **5. 多哲学对撞**: 6 视角 多/空/弃权 投票表 + 对撞结论（来自步骤 3.5）。
    - **质量记分卡定义**（每维 0-10 × 权重，加总 0-100；分带 → 等级）：

      | 维度 | 权重 | 得分(0-10) | 加权 | 依据 |
      | :--- | :--- | :--- | :--- | :--- |
      | 护城河宽度与趋势 | 30% | | | |
      | 资本回报 (ROIC/ROE 真实性) | 25% | | | |
      | FCF 质量与转化 | 20% | | | |
      | 管理层与本分文化 | 15% | | | |
      | 估值安全边际 | 10% | | | |
      | **合计** | 100% | — | **[N]/100** | |

      > 分带：≥85 A+ ｜ 75-84 A ｜ 60-74 B ｜ 45-59 C ｜ <45 D。`/update` 刷新时逐维对比，某维恶化 ≥2 分即记护城河侵蚀红旗。
    - **File Path**: `Reports/deepdive/[YYYYMMDD]_[Ticker]_Value.md`.
    - **Footer**: `**生成模型**: [IDE Agent] (gemini-3.1-pro-preview)`

5.  **Output**:
    - **先 `check_report_quality(markdown)`**；`passed: false` 时按 `missing_sections` / `issues` 补齐后重跑，通过后再用 `write_to_file` 保存到 `Reports/deepdive/[YYYYMMDD]_[Ticker]_Value.md`（落盘是必须动作，严禁只回复不保存）。
    - Present the "Quality Score" in the final answer (e.g., "A+ Compounder" or "B- Cyclical Trap").
    - 在通知末尾附加：
      > 💡 **强烈建议**: 质量复利分析是知识库中最有价值的内容类型（护城河/10年财务基线难以再次收集）。建议立即执行 `/add` 将核心结论、关键财务锚点、护城河判断保存到知识库。
