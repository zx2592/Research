# 命令手册 — 工作流命令详解

> 所有命令可通过 **IDE 斜杠命令**、**Telegram Bot** 或 **CLI**（`python research_cli.py <cmd> [args]`）触发。
> **报告归档**：`/deep`、`/value` → `Reports/deepdive/`（深度沉淀）；其余命令 → `Reports/YYYYMMDD/`（按日归档）。
> **模型**：`/deep`、`/value` 使用 gemini-3.1-pro；其余使用 gemini-3-flash。
> **语言**：所有输出使用中文（简体），Ticker 等专有名词保留英文。

---

## 一、市场发现类

### `/scan` — 市场全景扫描
**功能**：双引擎（RSS 情报 + 搜索引擎实时数据）采集市场信息，识别四类信号——主题收敛 / 高影响异常 / 认知温差 / 深度基石；板块猎手深挖龙头与跨市场映射。
**用法**：`/scan`
**报告**：`YYYYMMDD_Market_Scan.md`

### `/lead` — 市场领航者
**功能**：穿越雪球、Reddit 与专业研报的全球情绪共振审计。强制 **≥60% 新鲜外部线索**（防信息茧房），AI 提炼全网最靠谱的研究线索并生成领航报告。
**用法**：`/lead`、`/lead 机器人`（可选关键词聚焦）
**报告**：`YYYYMMDD_Market_Lead.md`

### `/theme` — A股主题发现
**功能**：识别当前最强主题方向，构建主题逻辑链（政策/产业/资金驱动），筛选可交易标的并给出梯队划分。
**用法**：`/theme`
**报告**：`YYYYMMDD_Theme_Discovery.md`

### `/core` — 核心持仓简报
**功能**：实时刷新核心持仓的报价、近期异动与逻辑稳固度。核心标的清单运行时读取本地 `Config/holdings.json`（被 `.gitignore` 忽略）。用于盘前/盘后的"核心资产扫描"。
**用法**：`/core`
**报告**：`YYYYMMDD_Core_Report.md`

---

## 二、个股研究类

### `/deep [Ticker]` — 个股深度研究　🔵 Pro
**功能**：三阶段深度分析 — A) 商业模式 + 护城河 + 增长驱动力 → B) 财务深度 + 盈利预测 + 动态 PE + 反向 DCF 估值 → C) 多空博弈压力测试 + 致命风险清单。
**用法**：`/deep NVDA`
**报告**：`deepdive/YYYYMMDD_NVDA_Deep.md`

### `/value [Ticker]` — 质量复利分析　🔵 Pro
**功能**：Buffett / 李录 / 段永平 / 达尔文框架 — 10 年财务数据 + 护城河深度 + 企业文化 + 估值锚点。专注长期持有型公司的质量评估。
**用法**：`/value MCO`
**报告**：`deepdive/YYYYMMDD_MCO_Value.md`

### `/quick [Ticker] [Event]` — 事件快评
**功能**：事件驱动的快速分析 — 信息分级（Class A/B）+ 边际变化（What/Why/Impact）+ 局势玩家扫描 + 投资推演 + 长线护城河/短线势能双轨策略。
**用法**：`/quick NVDA 财报超预期`
**报告**：`YYYYMMDD_NVDA_Quick.md`

### `/update [Ticker]` — 公司情报刷新
**功能**：定期补课 — 拉取目标公司最新财报/新闻/公告，汇总近期边际变化，校验投资逻辑，更新估值锚点。
**用法**：`/update NVDA`
**报告**：`YYYYMMDD_NVDA_Update.md`

### `/verify [Claim]` — 事实核查
**功能**：对市场传言或投资论断进行一手源搜索与交叉验证，给出 Confirmed / Falsified / Unverified 判决。
**用法**：`/verify NVDA will lose market share to AMD in 2027`
**报告**：`YYYYMMDD_Topic_Verify.md`

---

## 三、交易决策类

### `/buy [Ticker]` — 买入审计
**功能**：买入前全面审查 — 板块 Beta 熔断（向下直接驳回）+ 股性四项 Checklist + 策略定位 + 止损/目标/盈亏比计算 + 纪律合规（红线/信息洁癖）+ FOMO 自检 → 🟢通过 / 🟡观望 / 🔴驳回。
**用法**：`/buy NVDA`
**报告**：`YYYYMMDD_NVDA_Buy.md`

### `/sell [Ticker]` — 卖出审计
**功能**：卖出决策审查 — 入场定性回溯 + 风格漂移检查 + 5 类卖出信号扫描 + 纪律合规（红线/长线禁忌/短线禁忌）+ 4 种策略选项（止损/MoonBag/备兑/持有）+ 漂移自检。
**用法**：`/sell NVDA`
**报告**：`YYYYMMDD_NVDA_Sell.md`

### `/option [Ticker] [目标]` — 期权策略
**功能**：三大期权场景 — Covered Call（备兑增强）/ Cash Secured Put（低价接货）/ Protective Put（下跌保护），计算行权价 + Delta + 年化收益 + 盈亏场景。
**用法**：`/option NVDA 增强收益`
**报告**：`YYYYMMDD_NVDA_Option.md`

### `/macro [Event]` — 宏观压力测试
**功能**：宏观事件对持仓/个股的冲击评估 — 贴现率敏感度 + 业务传导机制 + 避险属性三维度压力测试，输出传导链 + 操作建议。
**用法**：`/macro 美联储加息50bp`
**报告**：`YYYYMMDD_Macro_Event.md`

---

## 四、组合管理类

### `/position` — 持仓体检
**功能**：组合健康度检查 — 量化绩效仪表盘（Sharpe/回撤/CAGR vs SPY）+ 收益贡献归因 + 研究新鲜度 + 定量相关性矩阵 + 集中度风险 + 再平衡建议 + HTML Tearsheet。
**用法**：`/position`
**报告**：`YYYYMMDD_Position_Analysis.md` + `YYYYMMDD_Position_Tearsheet.html`

### `/optimize [method]` — 组合优化
**功能**：基于 optimalportfolios 库计算最优权重（最大分散化 / 最小波动 / 最大 Sharpe / 风险平价），生成具体调仓交易清单，含风控校验和定性审视。
**用法**：`/optimize`、`/optimize minvol`、`/optimize maxsharpe`、`/optimize riskparity`
**报告**：`YYYYMMDD_Optimize_[Method].md`

---

## 五、复盘 / 知识类

### `/rethink [Ticker]` — 交易复盘
**功能**：交易结束后的系统性复盘 — 知行合一检查（买卖理由是否匹配）+ 运气 vs 实力区分 + SOP 漏洞诊断 → 0–10 纪律评分 + 核心教训 + 改进动作。漏洞自动追加到 `Feedback_Loop/Pattern_Log.md`。
**用法**：`/rethink NVDA`
**报告**：`YYYYMMDD_NVDA_Rethink.md`

### `/add` — 知识库留存
**功能**：提取当前研报的核心洞察，生成知识卡片保存到 `Memory_Layer/Knowledge_Base/`，可选同步到 Obsidian。
**用法**：`/add`
**报告**：`Memory_Layer/Knowledge_Base/[Topic]_[Date].md`

---

## 命令速查表

| 命令 | 参数 | 模型 | 分类 | 一句话 |
|:---|:---|:---:|:---|:---|
| `/scan` | — | Flash | 市场发现 | 市场全景 + 板块猎手 |
| `/lead` | 关键词? | Flash | 市场发现 | 全球情绪共振 + 新线索发现 |
| `/theme` | — | Flash | 市场发现 | A股主题方向 + 可交易标的 |
| `/core` | — | Flash | 市场发现 | 核心持仓实时简报 |
| `/deep` | Ticker | **Pro** | 个股研究 | 三阶段深度基本面 |
| `/value` | Ticker | **Pro** | 个股研究 | 质量复利框架 |
| `/quick` | Ticker + Event | Flash | 个股研究 | 事件快评 + 玩家推演 |
| `/update` | Ticker | Flash | 个股研究 | 公司情报刷新 |
| `/verify` | Claim | Flash | 个股研究 | 事实核查判决 |
| `/buy` | Ticker | Flash | 交易决策 | 买入审计 🟢🟡🔴 |
| `/sell` | Ticker | Flash | 交易决策 | 卖出审计 + 风格漂移 |
| `/option` | Ticker + 目标 | Flash | 交易决策 | 期权策略三场景 |
| `/macro` | Event | Flash | 交易决策 | 宏观压力测试 |
| `/position` | — | Flash | 组合管理 | 量化体检 + 归因 + 再平衡 |
| `/optimize` | method? | Flash | 组合管理 | 量化优化 + 交易清单 |
| `/rethink` | Ticker | Flash | 复盘改进 | 交易复盘 + 纪律评分 |
| `/add` | — | Flash | 知识管理 | 知识卡片留存 |
