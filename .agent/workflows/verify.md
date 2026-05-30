---
description: Verify a specific claim, news rumor, or data point using reliable sources (Template C).
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


1.  **Parse Arguments**:
    - Command: `/verify [Subject/Hypothesis]` (e.g., `/verify iPhone 18 titanium rumor`)

2.  **Define Verification Objective**:
    - **Hypothesis**: What exactly are we testing?
    - **Desired Outcome**: Proven, Disproven, or Ambiguous.

3.  **Agentic Execution (Evidence Chain)**:
    - **Search Strategy**:
        - Step 1: Broad search for the claim.
        - Step 2: Targeted search for *primary sources* (Company IR, Patent filings, Official statements).
        - Step 3: Cross-reference with credible tier-1 media (Bloomberg, Reuters, WSJ).

4.  **Synthesize Findings (Template C)**:
    - **Verdict**: [Confirmed / Falsified / Unverified]
    - **CRITICAL: The Report MUST be written in CHINESE (Simplified).**
    - **Evidence Chain**:
        - Evidence 1: [Source Link] - [Quote]
        - Evidence 2: [Source Link] - [Quote]
    - **Implication**: Impact on the related stock/sector.
    - **Confidence Score**: 1-10.

5.  **Output（必须按顺序执行，不可跳过）**:
    - **⚠️ 必须先保存再回复**：先调用 `write_to_file` 将完整核查报告写入 `Reports/[YYYYMMDD]/[YYYYMMDD]_[Subject]_Verify.md`，再在最终回答中展示摘要。**严禁只回复不保存。**
    - **报告格式**：使用 Template C，包含：Verdict、Evidence Chain（含来源链接）、Implication、Confidence Score。
    - **Footer**: `**生成模型**: [IDE Agent] (Gemini 2.5 Pro)`
    - **后续**: 若事件重大，询问用户是否 `/add` 保存到知识库。
