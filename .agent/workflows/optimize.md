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

如发现重大风险 → 在报告中标注 🔴 并建议跳过该调仓

---

## Step 4: 报告生成

```markdown
# [YYYYMMDD] 组合优化建议

> **优化方法：** [最大分散化 / 最小波动 / 最大Sharpe / 风险平价]
> **约束条件：** 单票 ≤15%、现金 ≥15%

## 1. 优化前后对比

| 指标 | 当前 | 优化后 | 改善 |
| :--- | :--- | :--- | :--- |
| 年化收益率 | X.X% | X.X% | +X.Xppt |
| 年化波动率 | X.X% | X.X% | -X.Xppt |
| Sharpe Ratio | X.XX | X.XX | +X.XX |
| HHI 集中度 | XXXX | XXXX | -XXX |

## 2. 权重变化明细

| Ticker | 策略桶 | 当前% | 目标% | 变化 | 动作 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [Ticker] | [桶] | X.X% | X.X% | +/-X.X% | 加仓/减仓/清仓/不动 |

## 3. 具体交易清单

| # | 动作 | Ticker | 股数 | 金额 | 理由 | 风控 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 卖出 | [Ticker] | XX | $XX,XXX | [原因] | ✅/⚠️/❌ |
| 2 | 买入 | [Ticker] | XX | $XX,XXX | [原因] | ✅/⚠️ |

## 4. 定性风险审视

对建议大幅加仓的标的进行搜索核查：
- **[Ticker]**: [搜索发现] → [无风险/有风险标记]

## 5. 执行建议

- 建议分 2-3 天执行，避免一次性大量调仓冲击成本
- **优先执行：** [最紧急的 1-2 笔，如超标减仓]
- **可选执行：** [优化但非必须的调仓]
- **暂缓执行：** [受限或有基本面风险的交易]

---
**生成时刻**: [YYYYMMDD HH:MM]
**优化引擎**: optimalportfolios + EWMA 协方差估算
```

**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_Optimize_[Method].md`

---

## Step 5: 保存与通知

1. 用 `write_to_file` 保存完整报告
2. 向用户展示精简总结：
   - 格式：`[组合优化] 方法: [X] | Sharpe: X.XX→X.XX | 建议交易: N笔 | 首要: [减仓/加仓 Ticker]`
