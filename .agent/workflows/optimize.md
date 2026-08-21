---
description: 组合优化 — 基于量化模型计算最优权重，生成具体调仓交易清单
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

> **契约**：本工作流的报告必须遵守注入在本文件之前的三份公共契约（报告结构 / 证据标准 / 质量门禁）。优化处方天然含前后指标与交易清单：**「数字底稿」= 权重变化明细 + 交易清单**。优化前后指标来自 optimizer（标来源 + 计算时间）；**大幅加仓标的的基本面必须有外部来源 + 时间**。

> **定位：** `/optimize` 是 `/position` 的"行动版"。
> - `/position` 告诉你"组合哪里有问题"（诊断）
> - `/optimize` 告诉你"具体怎么调仓"（处方）
>
> **运行环境适配：** 优化计算通过 `scripts/portfolio_optimizer.py` 执行，依赖 `optimalportfolios` 库。

## 解析参数

- `/optimize` — 默认最大分散化优化
- `/optimize minvol` — 最小波动率组合
- `/optimize maxsharpe` — 最大 Sharpe 比率组合
- `/optimize riskparity` — 风险平价（等风险贡献）
- `/optimize [自由文本]` — 如"减少 crypto 敞口到 20%"，Agent 解析后选择合适方法+约束

---

## Step 0: 上下文装配（0 次搜索）

1. 读取 `Config/我的投资状态卡.md` — 提取风险偏好、仓位目标、投资禁忌
2. 读取 `Config/我的关联偏好.md` — 提取已知关联关系
3. 读取 `Config/holdings.json` — 了解持仓结构和策略桶分类
4. 解析用户参数：
   - 识别优化方法（max_diversification / minvol / maxsharpe / riskparity）
   - 如为自由文本，Agent 判断最合适的方法和约束参数

---

## Step 1: 优化计算（0 次搜索）

通过 Bash 执行优化引擎：

```bash
python scripts/portfolio_optimizer.py \
  --method [方法] \
  --max-position 15 \
  --min-cash 15 \
  --days 252 \
  --output json
```

**参数说明：**
- `--method`: 优化目标（max_diversification / minvol / maxsharpe / riskparity）
- `--max-position 15`: 单票上限 15%（与 guards 对齐）
- `--min-cash 15`: 现金最低保留 15%（与投资状态卡对齐）
- `--days 252`: 使用过去一年数据估算协方差

**解读 JSON 结果：**
- `current_weights` vs `target_weights`: 当前与目标权重对比
- `trades`: 具体交易清单（ticker, action, shares, dollar_amount）
- `metrics_before` vs `metrics_after`: 优化前后的年化收益/波动率/Sharpe/HHI

---

## Step 2: 约束校验（0 次搜索）

对每笔建议交易，检查可执行性：

| 校验项 | 规则 | 处理 |
| :--- | :--- | :--- |
| 单票上限 | target_weight ≤ 15% | 不应触发（优化器已约束），如触发则标记 |
| 反向冷却 | 30 天内卖出后不能买回 | 查 `data/event_log/events.jsonl` 近期交易 |
| 交易冷却 | 同一 ticker 24h 内不能重复交易 | 查事件日志 |
| 最小交易额 | 交易金额 < $500 的跳过 | 不值得执行 |

标注每笔交易：✅ 可执行 / ⚠️ 受限（附原因）/ ❌ 不可执行

---

## Step 3: 定性审视（2-4 次搜索）

> 优化器只看历史数据，看不到基本面变化。对建议"大幅加仓"（delta > +3%）的票做快速核查。

对每只建议大幅加仓的标的（最多 3 只），执行一次搜索：
- 查询：`[Ticker] [公司名] recent news outlook risk [当月] [当年]`
- 目的：确认没有优化器看不到的负面催化剂（财务造假、监管风险、业绩暴雷等）

如发现重大风险 → 在报告中标注 🔴 并建议跳过该调仓。

> **这一步就是本报告的反方**：优化器只会告诉你「历史协方差说该加」，它不知道这家公司昨天被立案了。搜不到东西也要如实写「未发现负面催化剂（已搜 N 条）」，不能省略这一节。
> 搜索走 `search_web` / `browser_fetch`，每条结论带来源 + 时间 + 层级。

---

## Step 4: 报告生成

````markdown
# [YYYYMMDD] 组合优化建议

> **优化方法：** [最大分散化 / 最小波动 / 最大Sharpe / 风险平价]
> **约束条件：** 单票 ≤15%、现金 ≥15%

## 结论先行
- **一行判决**：`优化方法[X] · Sharpe X.XX→X.XX · 建议交易 N 笔 · 首要动作[减/加 Ticker] · 置信度[高/中/低]`
- **相对当前组合**：集中度 / Sharpe / 各策略桶权重的移动
- **价格证据**：[交易清单里的金额按什么价算的——按公共契约二选一如实写；单源未交叉时只给股数与目标权重，不给成交金额定价]

## 实时数据快照

| 项目 | 数值 | 来源 | 时间 |
| :--- | :--- | :--- | :--- |
| 持仓与现金 | | Config/holdings.json + get_portfolio_snapshot | |
| 优化结果 | | portfolio_optimizer.py --method X | |

## 证据台账（= 优化前后对比 + 定性审视）

| 关键判断 | 读数 / 证据 | 来源 | 时间 | 层级 | 对结论的影响 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Sharpe 改善 | X.XX → X.XX | optimizer | | T2 | |
| 波动率下降 | X.X% → X.X% | optimizer | | T2 | |
| HHI 下降 | XXXX → XXXX | optimizer | | T2 | |
| [大幅加仓标的] 无负面催化 | | search_web | | T1/T2/T3 | |

> **必含一行反方**：定性审视发现的风险，或「优化器只看历史」这一结构性局限对本次处方的影响。

## 1. 优化前后对比

| 指标 | 当前 | 优化后 | 改善 |
| :--- | :--- | :--- | :--- |
| 年化收益率 | X.X% | X.X% | +X.Xppt |
| 年化波动率 | X.X% | X.X% | -X.Xppt |
| Sharpe Ratio | X.XX | X.XX | +X.XX |
| HHI 集中度 | XXXX | XXXX | -XXX |

## 数字底稿（权重变化明细 + 交易清单）

### 权重变化明细
| Ticker | 策略桶 | 当前% | 目标% | 变化 | 动作 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [Ticker] | [桶] | X.X% | X.X% | +/-X.X% | 加仓/减仓/清仓/不动 |

### 具体交易清单
| # | 动作 | Ticker | 股数 | 金额 | 理由 | 风控 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 卖出 | [Ticker] | XX | $XX,XXX | [原因] | ✅/⚠️/❌ |
| 2 | 买入 | [Ticker] | XX | $XX,XXX | [原因] | ✅/⚠️ |

## 4. 定性风险审视

- **[Ticker]**: [搜索发现 + 来源 + 时间] → [无风险 / 🔴 建议跳过]

## Bull/Base/Bear（不同约束下的取舍）

| 情景 | 概率 | 假设 | 组合含义 | 触发条件 |
| :--- | :--- | :--- | :--- | :--- |
| Bull（相关性维持历史水平） | | | | |
| Base（本次处方） | | | | |
| Bear（相关性齐升，分散化失效） | | | | |

## 行动计划

- **优先执行**：[最紧急的 1-2 笔，如超标减仓] — 触发条件：[…]
- **可选执行**：[优化但非必须的调仓]
- **暂缓执行**：[受限或有基本面风险的交易]
- **执行节奏**：分 2-3 天执行，避免一次性大量调仓的冲击成本
- **看错信号**：[出现什么 = 本处方作废，例如某加仓标的爆出负面催化]
- **下次复盘点**：[日期 / 下次 `/position`]

## 风险与不确定性

[协方差估计对历史的依赖、未核查的中等调仓、交易冲击成本]

### 证据缺口

- [缺什么] — [影响哪笔交易] — [下一步去哪取]

## 质量自检

- `check_report_quality(markdown)` 结果：[passed]
- ✅ 质量Gate 8/8（或 ⚠️ N/8，未过项见上）

---
**生成时刻**: [YYYYMMDD HH:MM]
**优化引擎**: optimalportfolios + EWMA 协方差估算
````

**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_Optimize_[Method].md`

---

## Step 5: 保存与通知

1. 先 `check_report_quality(markdown)`；`passed: false` 时按 `missing_sections` / `issues` 补齐后重跑，通过后再用 `write_to_file` 保存完整报告
2. 向用户展示精简总结：
   - 格式：`[组合优化] 方法: [X] | Sharpe: X.XX→X.XX | 建议交易: N笔 | 首要: [减仓/加仓 Ticker]`
