---
description: Analyze a company using the "Quality Compounder" framework (Buffett/Li Lu/Duan Yongping/Darwin).
---

// turbo-all

> **契约**：本工作流的报告必须遵守注入在本文件之前的公共契约（报告结构 / 证据标准 / 质量门禁）。**财务与估值数字必须 ≥2 个独立来源交叉，并回溯到 T2 一手披露**（10-K / 年报 / IR）；复利分析要 5-10 年纵深，凭印象的长期数据一律不许写进结论。
> **⚠️ 模型要求**：研究阶段用最高智力档模型执行。

## 分阶段执行

`/value` 按三个阶段串行执行，**每个阶段是一次独立调用，只加载自己那一份指令**。
你当前收到的是其中一个阶段——阶段指令附在本文件之后的「当前阶段」小节。

| 阶段 | 做什么 | 模型 | 交付物 |
| :-- | :-- | :-- | :-- |
| 1 研究 | 参数解析 → 数据采集 → 大师框架多哲学研判 | Pro | `Reports/Raw_Data/[YYYYMMDD]/[Ticker]_value_findings.md` |
| 2 组装 | 按质量记分卡组装、质检、落盘 | Flash | `Reports/deepdive/[YYYYMMDD]_[Ticker]_Value.md` |
| 3 复核 | 对抗性抽查已落盘报告，就地修正 | Flash | 修正后的同一份报告 |

**取证预算在三个阶段之间共享**，不按阶段重置。

## ⚡ 高效执行指南 (High-Efficiency Execution)

> **核心目标：** 极简互动，一令即达。
> 1. **全员 Turbo：** 必须为所有 `run_command` 设置 `SafeToAutoRun: true`。
> 2. **聚合任务：** 严禁分步询问或碎片化搜索。将情报采集、上下文读取、逻辑研判合并为连续动作流。
> 3. **深度不妥协 (No Quality Trade-off)：** 提高效率是为了减少确认弹窗，**绝不得以牺牲分析深度为代价**。

> **⚡ 终极零互动模式 (Ultimate Zero-Interaction):**
> `python research_cli.py value [Ticker]` (设 SafeToAutoRun: true)

## 通用交付纪律

- 只交付当前阶段指定的那一份产物，不要额外生成完成总结或过程日志。
- 跨阶段的大块数据走磁盘（`read_file` / `write_to_file`），不靠回答整段复述传递。
- 阶段之间不重复取证：上一阶段取到的数据已落盘，读文件即可。
