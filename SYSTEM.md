# AI Investment Research System — 系统说明

> **定位**: 专家级投研大脑，整合 Trigger Engine、社交舆情智能与 17 个核心 Workflow 体系。
> 详细命令用法见 `COMMANDS.md`，整体介绍见 `README.md`。

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   用户入口 (Entry Points)                │
├───────────────────────┬─────────────────────────────────┤
│     Telegram Bot      │  CLI                            │
│     (对话/命令)        │  python research_cli.py         │
└───────────┬───────────┴───────────────┬─────────────────┘
            │                           │
            ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│              第一层：Eyes (信息获取)                      │
│  RSS订阅 | yfinance | tushare | Tavily | Brave Search   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              第二层：Brain (LLM 处理)                     │
│  google-genai SDK (gemini-3-flash / gemini-3.1-pro)     │
│  Skills: V1 7命令 + Core P1-P15 + 工作流暗号            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              第三层：Memory (知识归档)                     │
│  Reports/ | Config/ai建议 | Knowledge_Base | Obsidian   │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 命令体系

### 核心工作流 (Workflows — 17 个)
| 命令 | 说明 | Workflow 路径 |
|:---|:---|:---|
| `/scan` | 市场全景扫描 | `.agent/workflows/scan.md` |
| `/lead` | 全球社交/情绪共振领航 | `.agent/workflows/lead.md` |
| `/theme` | A股主题发现 | `.agent/workflows/theme.md` |
| `/core` | 核心持仓简报 | `.agent/workflows/core.md` |
| `/deep [Tick]` | 个股深度研究 (Pro) | `.agent/workflows/deep.md` |
| `/value [Tick]` | 质量复利分析 (Pro) | `.agent/workflows/value.md` |
| `/quick [Tick]` | 事件/异动快评 | `.agent/workflows/quick.md` |
| `/update [Tick]` | 公司边际变化对齐 | `.agent/workflows/update.md` |
| `/verify [Claim]` | 事实核查 | `.agent/workflows/verify.md` |
| `/buy [Tick]` | 买入决策风险审计 (GuardChain) | `.agent/workflows/buy.md` |
| `/sell [Tick]` | 卖出决策退出审计 | `.agent/workflows/sell.md` |
| `/option [Tick]` | 期权策略三场景 | `.agent/workflows/option.md` |
| `/macro [Event]` | 宏观冲击压力测试 | `.agent/workflows/macro.md` |
| `/position` | 持仓深度体检 (HHI/Freshness) | `.agent/workflows/position.md` |
| `/optimize [method]` | 组合优化 + 调仓清单 | `.agent/workflows/optimize.md` |
| `/rethink [Tick]` | 交易反思与纠偏 | `.agent/workflows/rethink.md` |
| `/add` | **知识飞轮入口** (存档至 KB) | `.agent/workflows/add.md` |

### 自然语言暗号 (Natural Language Signals)
| 暗号 | 说明 | 触发 |
|:---|:---|:---|
| "跑一下市场洞察" | 市场洞察报告 | RSS → P13 → Report |
| "调研一下 [股票]" | 个股基石建档 | P1 Genesis |
| "这个是PVP还是PVE" | 判断势能类型 | P2 Phase Check |
| "我想买 [股票]" | FOMO 杀手审计 | P5 |
| "我想卖 [股票]" | 利润守门员 | P6 |
| "做个持仓体检" | 持仓健康度 | P7 |
| "估值贵不贵" | 反向 DCF | P9 |
| "复盘一下" | 交易尸检 | P11 |
| "找个板块" | 板块猎手 | P14 |

---

## 3. LLM 模式（API 驱动）

系统统一通过 google-genai SDK 调用 Gemini API（不再有桌面 IDE 模式）：

| 调用方式 | 默认模型 |
|:---|:---|
| google-genai SDK | gemini-3-flash（常规）/ gemini-3.1-pro（`/deep`、`/value`） |

主/备 Key 通过 `.env` 中 `GEMINI_API_KEY` / `GEMINI_API_KEY_BACKUP` 配置；主 Key 失败自动回退备用 Key。

**多 Provider**：`core/llm_providers.py` 支持 OpenAI 兼容接口（`openai` / `openrouter` / `qwen`），经 `LLM_PROVIDER` 切换。纯文本对话与工具调用（function calling，经手动工具循环驱动）均已接通，工作流可正常运行。详见 `README.md` 环境变量表。

---

## 4. 数据源

| 渠道 | 类型 | 说明 |
|:---|:---|:---|
| RSS Subscription | 被动订阅 | Default + 核心自研 RSS 汇总 |
| **bb-browser** | 社交舆情 | 基础引擎，用于非结构化抓取与 UI 交互 |
| yfinance | 主动拉取 | 美/港/日/A 股行情与财务数据（`intl-vendor` 族）|
| 腾讯行情 | 主动拉取 | A股/港股/美股实时快照，交叉验证的跨族第二来源（`cn-exchange-relay` 族）|
| 东方财富 | 主动拉取 | A股 52 周区间、估值指标与结构化年报（`cn-exchange-relay` 族）|
| tushare | 主动拉取 | A 股基本面与公告 |
| Tavily / Brave | 搜索引擎 | 主力/备用搜索 |
| KnowledgeHub | 本地知识库 | 通过 KB_INDEX 预检，命中则跳过冗余搜索 |

---

## 5. 报告归档结构

```
Reports/
├── Raw_Data/YYYY-MM/            ← 原始数据 JSON
├── Internal_Report/YYYY-MM/     ← 洞察报告 (Core 格式)
└── YYYYMMDD/                    ← 日报/研报 (V1 格式)

Config/ai建议/                   ← 投资雷达
Memory_Layer/Knowledge_Base/     ← 知识卡片 (/add)
Obsidian_Vault/                  ← Obsidian 同步 (可选)
```

---

## 6. 自动化

- **Market Sentinel**: `sentinel/market_sentinel.py` - 定时扫描市场异动
- **Telegram Bot**: `bot/telegram_bot.py` - 对话式命令 + 推送通知
- **Bot Service**: `bot/bot_service.py` - 后台自动重启

---

## 7. 绝对规则

1. 所有输出必须使用**中文(简体)**，专有名词可保留英文
2. 每个命令必须生成 Markdown 文件，不可仅打印到控制台
3. 使用日历年 (CY) 标注时间，如果是财年需明确标注
4. 搜索限额：每个任务最多 8 次搜索调用
5. 数据必须交叉验证，避免幻觉——价格用 `cross_validate_price`、财务指标用 `cross_validate_metric`；**同族来源互比不算交叉**（腾讯/东财/新浪/同花顺/雪球转发同一份交易所行情），未交叉时如实申报单源，不得给出目标价、止损与盈亏比
6. **防止过拟合 (Anti-Overfitting)**：在执行发现类任务（如 `/lead`, `/scan`, `/theme`）时，必须优先扫描全场信号，**严禁**仅围绕“自选股/持仓”进行复读。新发现线索占比必须符合各个 Workflow 的具体要求（通常 ≥60%）。
7. **数据优先 (Data First)**：在社交抓取失败时，应如实报告数据缺失，严禁通过“脑补”用户已知信息来填充报告。
8. **逻辑强制归类 (Logic Categorization)**：所有投资建议和审计结论必须首行明确归类到「第8节」定义的 6 大母类之一。

---

## 8. 投资逻辑分类标准 (Invest DNA)

所有投资机会必须归属以下母类之一：

1. **左侧博弈 (Contrarian/Left-side)**: 阴跌或横盘中基于估值极低、困境反转或预期差提前进场。
2. **右侧确认 (Momentum/Right-side)**: 趋势扭转（突破均线/前高）后买入，优先考虑动能而非价格。
3. **长线护城河 (Core Moat/Quality)**: 买入并持有具备绝对竞争优势的公司（如 Hermes, Google），赚取内生增长。
4. **宏观动能 (Macro/Cycle)**: 基于利率、地缘、大宗商品周期或行业政策转向的配置（如油轮、比特币）。
5. **套利/确定性 (Arbitrage/Certainty)**: 利用定价偏离、分红套利、拆分重组或确定性事件获利。
6. **短线脉冲 (Catalyst/Pulse)**: 基于突发新闻、财报预期博弈或情绪极值的超短线交易。

---

## 9. 减仓/退出风格

1. **落袋为安 (Profit Lock)**: 达到目标价或估值进入过热区间。
2. **均线熔断 (Trend Breakdown)**: 技术面走弱（跌破关键位/均线/死叉）强制退出。
3. **逻辑破缺 (Thesis Erosion)**: 原买入逻辑消失或基本面恶化（如核心指标转负）。
4. **调仓换股 (Alpha Rotation)**: 发现赔率更高、势能更强的替换标的。
5. **风控降噪 (Risk Trimming)**: 为维持组合配比或降低波动而进行的被动减仓。
