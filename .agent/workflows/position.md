---
description: 持仓体检 — 量化绩效仪表盘、收益归因、研究新鲜度校验、集中度风险评估、定量相关性矩阵、动态再平衡建议
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


> **运行环境适配：** 本 workflow 专注于组合层面的全局审计，要求数据实时性高。
> - **IDE 模式**：通过 `get_portfolio_snapshot()` 获取实时持仓，支持搜索最新行业观点进行相关性校验。
> - **VPS 模式**：通常作为定期任务执行（如每周五收盘后），通过 `PortfolioLedger` 提供的数据生成周报底稿。

## Step 0: 上下文装配

执行持仓体检前，必须加载以下上下文以建立“基准”：

1. **组合快照**：调用 `get_portfolio_snapshot()`。记录 `total_nav`, `cash`, 以及每个标的的 `shares`, `avg_cost`, `market_value`, `weight_pct`。
2. **知识库索引**：读取 `Memory_Layer/Knowledge_Base/KB_INDEX.md`。获取持仓标的的「最后更新日期」。
3. **风控规则**：读取 `services/execution/guards.py`。确认系统硬风控上限（如 `max_pct` 默认 15.0）。
4. **个性化偏好**：读取 `Config/我的投资状态卡.md` 和 `Config/我的关联偏好.md`。

---

## Step 1: 资产分布与比例审计

分析 `snapshot` 数据，将其归纳为以下视图：

### 1.1 现金与仓位水位
- **当前仓位百分比**: $(1 - \text{cash} / \text{total_nav}) \times 100\%$
- **现金防御力**: 当前现金能支撑多少次满格买入（基于 `max_pct`）？
- **对比基准**: 检查 `我的投资状态卡.md` 中的「目标仓位范围」。

### 1.2 定性分类审计
根据 `tags` 或文件名规则将持仓分类：
- **核心仓 (Core)**: 长期持有，稳健增长。
- **卫星仓 (Satellite)**: 主题性、高波动、短线。
- **定性一致性核查**: 检查是否有持仓在 `Trade_Records` 中定义为短线，但持有时间已超过预期且处于浮亏状态？（识别“被动长线”漏洞）

---

## Step 1.5: 量化绩效仪表盘（quantstats 驱动）

> **目的**: 用量化指标客观衡量组合表现，对标 SPY 基准，识别系统性问题。

### 1.5.1 核心绩效指标

通过 Bash 执行计算引擎：
```bash
python scripts/portfolio_metrics.py --mode metrics --days 252 --output json
```

将 JSON 结果填入以下表格（所有百分比保留一位小数，比率保留两位小数）：

| 指标 | 组合 | 基准(SPY) | 超额 |
| :--- | :--- | :--- | :--- |
| YTD 收益率 | X.X% | X.X% | +/-X.X% |
| CAGR (年化) | X.X% | X.X% | +/-X.X% |
| Sharpe Ratio | X.XX | X.XX | — |
| Sortino Ratio | X.XX | — | — |
| 最大回撤 | -X.X% | -X.X% | — |
| 年化波动率 | X.X% | X.X% | — |
| Beta | X.XX | 1.00 | — |
| Alpha (年化) | X.X% | — | — |
| 胜率 (日) | X.X% | — | — |
| VaR (95%) | -X.X% | — | — |

**快速诊断规则**:
- Sharpe < 0.5 → 🔴 风险调整收益不佳
- Beta > 1.5 → 🟡 组合比大盘波动大 50%+
- 最大回撤 > -20% → 🔴 需要风控审查

### 1.5.2 收益贡献度（过去 30 天）

```bash
python scripts/portfolio_metrics.py --mode contribution --period 30 --output json
```

将结果按贡献度从高到低排列：

| Ticker | 权重 | 30天收益 | 组合贡献(bps) | 占总收益% |
| :--- | :--- | :--- | :--- | :--- |
| [贡献最多] | X.X% | +X.X% | +XX.X | XX% |
| ... | | | | |
| [拖累最多] | X.X% | -X.X% | -XX.X | -XX% |

**诊断规则**:
- 单票贡献 > 50% 总收益 → 收益来源过于集中
- 尾部 3 只合计拖累 > 100bps → 考虑止损或 `/update` 审查

### 1.5.3 HTML Tearsheet（可选，仅 IDE 模式）

```bash
python scripts/portfolio_metrics.py --mode tearsheet --output Reports/YYYYMMDD/YYYYMMDD_Position_Tearsheet.html
```

生成完整 quantstats HTML 报告，包含月度热力图、滚动 Sharpe、回撤分析等可视化图表。在报告末尾附链接。

---

## Step 2: 研究新鲜度审计（核心强化）

利用 `KB_INDEX.md` 检查每个持仓的“维护状态”：

- **新鲜 (Fresh)**: 过去 2 周内有 `/deep`、`/update` 或 `/quick`。
- **待观察 (Notice)**: 2-4 周未更新。
- **过期 (Expired)**: 超过 1 个核心月（4 周）未进行系统性对齐。
- **研究缺失 (Missing)**: 在 Knowledge_Base 中找不到该标的的档案。

> **逻辑**: 买股票就是买逻辑。如果逻辑底稿超过一个月没更新，说明你对该标的的认知已处于“盲区”运行状态。

---

## Step 3: 风险矩阵扫描

### 3.1 集中度量化 (HHI 指数)
- **计算 HHI**: 将所有持仓占比（百分比）平方后加总。
  - $HHI < 1000$: 高度分散。
  - $1000 - 1800$: 适中。
  - $> 1800$: 高度集中（风险集中）。
- **单兵突破核查**: 识别任何占比接近或超过 `max_pct` (15%) 的标的。

### 3.2 行业与定量相关性分析
- **行业集中度**: 统计前三大行业的总占比。

- **定量相关性矩阵**:
  通过 Bash 执行：
  ```bash
  python scripts/portfolio_metrics.py --mode correlation --output json
  ```
  将 top 10 高相关对填入以下表格：

  | 高相关对 | 相关系数 | 合计权重 | 风险等级 |
  | :--- | :--- | :--- | :--- |
  | [Ticker A] ↔ [Ticker B] | X.XXX | XX.X% | 🔴/🟡/🟢 |

  **判定规则**:
  - 相关系数 > 0.8 且合计权重 > 10% → 🔴 高风险（实质同一笔交易）
  - 相关系数 > 0.6 且合计权重 > 15% → 🟡 注意
  - 其他 → 🟢 可接受

- **隐形关联扫描**:
  - 对照 `我的关联偏好.md` 中的关联网关系（如 A 跌则 B 损），检查组合当前的共振风险。
  - 将定量结果与定性判断交叉验证。

---

## Step 4: 动态再平衡建议

根据以上审计，生成具体的行动指引。建议分为三个优先级：

- **紧急 (Critical)**: 
  - 仓位超标（Weight > max_pct）→ **必须减仓**。
  - 触发了 `ReverseCooldownGuard` 的反向买入。
- **策略 (Strategic)**:
  - 研究高度过期（Expired）的持仓 → **建议执行 `/update`**。
  - 核心仓与卫星仓比例严重失衡。
- **优化 (Tactical)**:
  - 行业拥挤度过高，建议分散。
  - 现金流量管理。

---

## Step 5: 生成深度分析报告

```markdown
# [YYYYMMDD] AlphaSystem 组合深度体检

## 1. 组合概览与水位 (Portfolio Health)
| 指标 | 当前值 | 目标/基准 | 状态 |
| :--- | :--- | :--- | :--- |
| 总净值 (NAV) | $XXXX | - | - |
| 整体仓位 | XX.X% | [X% - X%] | 🟢/🟡/🔴 |
| 现金比例 | XX.X% | > 15% | 🟢/🔴 |
| HHI 集中度指数 | XXXX | < 1800 | [状态评价] |

## 1.5 量化绩效仪表盘 (Performance Dashboard)

### 核心指标 vs SPY
| 指标 | 组合 | SPY | 超额 |
| :--- | :--- | :--- | :--- |
| YTD | X.X% | X.X% | +/-X.X% |
| CAGR | X.X% | X.X% | +/-X.X% |
| Sharpe | X.XX | X.XX | — |
| 最大回撤 | -X.X% | -X.X% | — |
| Beta | X.XX | 1.00 | — |
| Alpha | X.X% | — | — |

### 30 天收益贡献 Top 3 / Bottom 3
| Ticker | 贡献(bps) | 30天收益 |
| :--- | :--- | :--- |
| [Top 1] | +XX.X | +X.X% |
| [Top 2] | +XX.X | +X.X% |
| [Top 3] | +XX.X | +X.X% |
| [Bottom 3] | -XX.X | -X.X% |
| [Bottom 2] | -XX.X | -X.X% |
| [Bottom 1] | -XX.X | -X.X% |

## 2. 研究新鲜度监控 (Research Freshness)
| 标的 | 最近分析日期 | 状态 | 建议动作 |
| :--- | :--- | :--- | :--- |
| [Ticker] | YYYY-MM-DD | 🟢 Fresh | 保持 |
| [Ticker] | YYYY-MM-DD | 🔴 Expired | **执行 /update** |
| [Ticker] | N/A | ⚪ Missing | **执行 /deep** |

## 3. 风险扫描结果
### ⚠️ 集中度风险
- [标的A] 占比 XX.X%，已触及风控红线 (15%)。
- 前三大行业 [行业名] 合计占比 XX%，存在结构性风险。

### 🔍 相关性穿透
- **识别风险**: 持仓中 [Ticker1] 与 [Ticker2] 均高度依赖 [宏观因子/上游]，实际风险敞口重合。
- **关联偏好校验**: [检查结果，是否违背禁忌]

## 4. 再平衡执行清单 (Execution List)

### 🔴 紧急处理
1. **[Ticker] 强制减仓**: 将占比从 XX.X% 削减至 15% 以下。
2. **[Ticker] 止损/清理**: [描述理由]

### 🟡 核心维护
1. 对 [Ticker] 执行一次 `/update`，该标电已有一个月未对齐最新边际变化。
2. 提高现金占比，以应对 [Step 3 识别出的宏观风险]。

### 🟢 调仓待办
1. ...

---
> 📊 完整 HTML Tearsheet: `Reports/YYYYMMDD/YYYYMMDD_Position_Tearsheet.html`

**生成时刻**: [YYYYMMDD HH:MM]
**数据源**: PortfolioLedger SQLite (Live) + quantstats + yfinance
```

**文件路径**: `Reports/YYYYMMDD/YYYYMMDD_Position_Analysis.md`

## Step 4: 保存与通知

1. **Write**: 使用 `write_to_file` 保存完整分析。
2. **Notify**: 向用户推送精简总结。
   - 格式：`[组合体检] NAV: XXX | 仓位: XX% | 风险点数: N | 首要行动: XXX`
3. **KB 更新**: 若分析中包含对组合策略的重大修正，提示用户使用 `/add` 保存到 `Investment_Persona.md`。
