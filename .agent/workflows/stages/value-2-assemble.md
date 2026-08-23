# /value 阶段二：报告组装与落盘

## 本阶段的输入

研究阶段已把分维度结论落盘到 `Reports/Raw_Data/[YYYYMMDD]/[Ticker]_value_findings.md`。
**先 `read_file` 读取该文件**，再按下面的规范组装报告。不要重新取证——
预算是共享的，研究阶段已经花过。

## 本阶段不做的事

- ❌ 不要重新搜索已经取到的数据
- ❌ 不要改写研究阶段的打分；发现打分有问题，在「风险与不确定性」中说明
- ❌ 不要额外产出完成总结、执行摘要独立文件

---

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
