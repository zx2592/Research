---
description: 期权策略建议 — 备兑增强、现金担保Put、保护性Put 三大场景
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

- `/option [Ticker] [Objective]`
- 例: `/option NVDA 增强收益` / `/option TSLA 低价抄底` / `/option AAPL 下跌保护`

---

## Step 1: 确认场景

| 场景 | 适用条件 | 策略方向 |
| :--- | :--- | :--- |
| **A 备兑增强** (Covered Call) | 持有正股，短期看涨但不想卖飞 | 卖虚值 Call |
| **B 现金担保 Put** (Cash Secured Put) | 看好但嫌贵，想低价接货 | 卖 Put |
| **C 保护性 Put** (Protective Put) | 持有正股，担心短期下跌 | 买虚值 Put |

**搜索动作**: 当前股价、IV（隐含波动率）、期权链数据

---

## Step 2: 策略设计

### 场景 A: 备兑增强 (Covered Call)
- 卖出 Delta ≈ 0.2-0.3 的虚值 Call
- 计算年化静态收益率
- **风险**: 最大潜在踏空利润

### 场景 B: 现金担保 Put (Cash Secured Put)
- Strike Price = 意向买入价
- 计算权利金收益
- **风险**: 如果大跌，是否愿意以行权价买入？

### 场景 C: 保护性 Put (Protective Put)
- 买入虚值 Put 作保险
- 计算保险成本占持仓比例
- **风险**: 横盘/上涨时保险费损失

---

## 输出报告

```markdown
# [YYYYMMDD] [Ticker] 期权策略

> **推荐策略：** [Covered Call / Cash Secured Put / Protective Put]

## 1. 当前状况
| 项目 | 数值 |
| :--- | :--- |
| 当前股价 | $... |
| 持仓成本 | $... |
| IV (隐含波动率) | ...% |

## 2. 策略参数
| 参数 | 数值 |
| :--- | :--- |
| 行权价 (Strike) | $... |
| 到期日 | YYYY-MM-DD (X周后) |
| Delta | ... |
| 权利金 | $... |
| 年化收益率 | ...% |

## 3. 盈亏场景
| 场景 | 结果 |
| :--- | :--- |
| 股价上涨超行权价 | ... |
| 股价小幅波动 | ... |
| 股价大跌 | ... |

## 4. 执行建议
- 具体操作步骤: ...
- 风险提示: ...

---
**生成模型**: [IDE Agent] (Gemini 2.5 Flash)
```

**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_[Ticker]_Option.md`

---

## 保存与通知

1. 用 `write_to_file` 保存报告
2. 在最终回答中展示推荐策略 + 关键参数 + 盈亏场景
