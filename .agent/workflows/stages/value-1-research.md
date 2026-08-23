# /value 阶段一：研究与取证

本阶段完成参数解析、数据采集与「大师框架」多哲学研判，**不写正式报告**。
报告组装规范在阶段二加载。

## 本阶段的交付物

把分维度结论落盘到 `Reports/Raw_Data/[YYYYMMDD]/[Ticker]_value_findings.md`
（该目录不受报告门禁约束）。内容按下列骨架组织：

```markdown
# [Ticker] 质量复利中间产物 [YYYYMMDD]

## 取证清单
| 取到的数据 | 来源 | 抓取时间 | 等级 | 用在哪个判断 |

## Circle of Competence / Moat / Management / Valuation Anchor 四维结论
## 多哲学对撞：6 视角投票表与对撞结论
## 质量记分卡：五维打分与依据（含 valuation_math.py 输出原文）
## 未取到的数据与原因
```

**估值脚本的 JSON 输出要原样贴进来**，阶段二直接引用，不必重跑。

## 交接说明（本阶段最后必须输出）

1. 中间产物文件的完整路径；
2. Quality Score 与评级倾向；
3. 哪些长期数据没取到、对哪一维打分有影响。

## 本阶段不做的事

- ❌ 不要写正式报告，也不要写到 `Reports/deepdive/`
- ❌ 不要调用 `check_report_quality`（阶段二才需要）
- ❌ 不要跳过护城河侵蚀核查——它是阶段二反方证据的主要来源

---

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
    - **估值算术必须走脚本**：`execute_python_script("scripts/valuation_math.py", "--market-cap <市值> --shares <总股本> --fcf <基期FCF> --discount-rate 0.10 --terminal-growth 0.03 --years 10")`。
      隐含增长率、安全边际价、终值占比、敏感性矩阵一律抄脚本输出，不得心算；
      `status: fail` 必须先修正输入再重跑，`status: warn` 的每一条都要在报告里正面回应。
      脚本只做算术——「这个增长率是否可信」仍由你判断。

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

