# /position 报告骨架

> 本文件是 `/position` 的报告骨架与保存流程。**做完前面的分析步骤、准备写报告时
> 才用 `read_file` 读取本文件**——分析阶段用不到它，提前载入只会让每一轮
> 工具循环都多背几 KB。

## Step 5: 生成深度分析报告

````markdown
# [YYYYMMDD] 组合深度体检

## 结论先行
- **一行判决**：`组合健康度[🟢健康/🟡需维护/🔴告急] · 首要行动 · 风险点 N 个 · 置信度[高/中/低]`
- **相对上次体检**：仓位 / HHI / Sharpe / 新鲜度的变化（无历史标「🆕首次体检」）
- **价格证据**：[持仓市值来自 get_portfolio_snapshot + 行情源；给具体减仓价位时按公共契约二选一如实写]

## 实时数据快照

| 项目 | 数值 | 来源 | 时间 |
| :--- | :--- | :--- | :--- |
| 总净值 NAV / 现金 | | get_portfolio_snapshot | |
| 绩效指标 | | portfolio_metrics.py --mode metrics | |
| 收益贡献 | | portfolio_metrics.py --mode contribution | |
| 相关性矩阵 | | portfolio_metrics.py --mode correlation | |

## 1. 组合概览与水位 (Portfolio Health)
| 指标 | 当前值 | 目标/基准 | 状态 |
| :--- | :--- | :--- | :--- |
| 总净值 (NAV) | $XXXX | - | - |
| 整体仓位 | XX.X% | [X% - X%] | 🟢/🟡/🔴 |
| 现金比例 | XX.X% | > 15% | 🟢/🔴 |
| HHI 集中度指数 | XXXX | < 1800 | [状态评价] |

## 数字底稿（量化绩效仪表盘）

### 核心指标 vs SPY
| 指标 | 组合 | SPY | 超额 | 来源 | 时间 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| YTD | X.X% | X.X% | +/-X.X% | quantstats | |
| CAGR | X.X% | X.X% | +/-X.X% | | |
| Sharpe | X.XX | X.XX | — | | |
| Sortino | X.XX | — | — | | |
| 最大回撤 | -X.X% | -X.X% | — | | |
| 年化波动率 | X.X% | X.X% | — | | |
| Beta | X.XX | 1.00 | — | | |
| Alpha | X.X% | — | — | | |
| 胜率 (日) | X.X% | — | — | | |
| VaR (95%) | -X.X% | — | — | | |

### 30 天收益贡献 Top 3 / Bottom 3
| Ticker | 权重 | 贡献(bps) | 30天收益 | 占总收益% |
| :--- | :--- | :--- | :--- | :--- |
| [Top 1] | | +XX.X | +X.X% | |
| [Bottom 1] | | -XX.X | -X.X% | |

## 证据台账（= 指标诊断与风险扫描）

| 关键判断 | 读数 / 证据 | 来源 | 时间 | 层级 | 对结论的影响 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Sharpe < 0.5? | | quantstats | | T2 | |
| Beta > 1.5? | | | | | |
| 最大回撤 > −20%? | | | | | |
| 单票超 max_pct(15%)? | | get_portfolio_snapshot | | T1 | |
| 高相关对 >0.8 且合计权重 >10%? | | correlation | | T2 | |

> **必含一行反方**：**组合当下最大的隐患**（哪怕总体健康）。

## 关键变化

| 维度 | 上次体检 | 当前 | 变化 |
| :--- | :--- | :--- | :--- |
| 仓位 / HHI / Sharpe / 过期标的数 | | | ⬆️/⬇️/↔️ / 🆕首次 |

## 2. 研究新鲜度监控 (Research Freshness)
| 标的 | 最近分析日期 | 状态 | 建议动作 |
| :--- | :--- | :--- | :--- |
| [Ticker] | YYYY-MM-DD | 🟢 Fresh | 保持 |
| [Ticker] | YYYY-MM-DD | 🔴 Expired | **执行 /update** |
| [Ticker] | 无档案 | ⚪ Missing | **执行 /deep** |

## 3. 风险扫描结果
### ⚠️ 集中度风险
- [标的A] 占比 XX.X%，已触及风控红线 (15%)。
- 前三大行业 [行业名] 合计占比 XX%，存在结构性风险。

### 🔍 相关性穿透
- **识别风险**: [Ticker1] 与 [Ticker2] 均高度依赖 [宏观因子/上游]，实际风险敞口重合。
- **关联偏好校验**: [检查结果，是否违背禁忌]

## Bull/Base/Bear（组合压力情景）

| 情景 | 概率 | 假设 | 组合预估回撤（按 Beta 推算） | 最脆弱标的 |
| :--- | :--- | :--- | :--- | :--- |
| Bull（大盘 +10%） | | | | |
| Base | | | | |
| Bear（大盘 −10% / −20%） | | | | |

## 行动计划（= 再平衡执行清单）

### 🔴 紧急处理
1. **[Ticker] 强制减仓**: 将占比从 XX.X% 削减至 15% 以下 —— 触发条件：[…]
2. **[Ticker] 止损/清理**: [理由 + 触发价]

### 🟡 核心维护
1. 对 [Ticker] 执行一次 `/update`（研究已过期）。
2. 提高现金占比，以应对 [识别出的宏观风险]。

### 🟢 调仓待办
1. ...

- **触发器**：减仓 / 止损 / `/update` / 补现金 各自的具体条件
- **看错信号**：[出现什么 = 本次体检结论作废]
- **下次复盘点**：[日期 / 下个周五收盘]

## 风险与不确定性

[相关性数据时效、绩效指标的历史依赖、缺档案的标的]

### 证据缺口

- [缺什么（如某标的无 KB 档案 / 某指标未取到）] — [影响哪个判断] — [下一步去哪取]

## 质量自检

- `check_report_quality(markdown)` 结果：[passed]
- ✅ 质量Gate 8/8（或 ⚠️ N/8，未过项见上）

---
> 📊 完整 HTML Tearsheet: `Reports/YYYYMMDD/YYYYMMDD_Position_Tearsheet.html`

**生成时刻**: [YYYYMMDD HH:MM]
**数据源**: PortfolioLedger SQLite (Live) + quantstats + yfinance
````

**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_Position_Analysis.md`

## Step 6: 保存与通知

1. **Write**: 先 `check_report_quality(markdown)`；`passed: false` 时按 `missing_sections` / `issues` 补齐后重跑，通过后再用 `write_to_file` 保存完整分析。
2. **Notify**: 向用户推送精简总结。
   - 格式：`[组合体检] NAV: XXX | 仓位: XX% | 风险点数: N | 首要行动: XXX`
3. **KB 更新**: 若分析中包含对组合策略的重大修正，提示用户使用 `/add` 保存到 `Investment_Persona.md`。
