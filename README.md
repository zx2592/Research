<div align="center">

# AlphaSystem

### 可审计、可复用的 AI 投资研究工作台

将多源市场数据、LLM 驱动的研究 SOP、知识沉淀、组合账本与执行风控组织成一套完整的投研系统。

[快速开始](#快速开始) · [系统架构](#系统架构) · [研究工作流](#研究工作流) · [研究质量保障](#研究质量保障) · [配置](#配置) · [路线图](#路线图) · [贡献](#贡献)

**当前版本 V4.4** · [版本历史](CHANGELOG.md)

</div>

> [!IMPORTANT]
> AlphaSystem 目前是面向个人研究与工程实验的项目，不构成投资建议，也不保证数据、模型输出或交易执行的准确性。涉及资金的操作必须由使用者独立核验并自行承担风险。

> [!NOTE]
> 仓库当前未提供 `LICENSE` 文件。在许可证补充前，请不要默认将代码视为已获得标准开源授权。

## Why AlphaSystem

传统投研工具往往把数据采集、分析提示词、报告归档和交易记录分散在不同应用中。AlphaSystem 将这些环节收敛到一条可追踪的研究链路：

- **从信号到结论**：统一接入行情、搜索、RSS、公告和社交信息，并通过缓存减少重复请求。
- **从结论到证据**：17 个研究工作流把市场扫描、个股深研、事实核查、交易审计和组合复盘固化为可复用 SOP，全部受统一的报告契约、证据契约与质量门约束。
- **从"取到数"到"取到能交叉的数"**：交叉验证按**来源族**判独立性——同一份交易所行情的多个门面互相比对不算交叉，价格结论必须申报交叉与否。
- **从一次分析到长期记忆**：报告、知识卡片、持仓事件与组合快照保留研究上下文。
- **从建议到受控执行**：可选执行管线在订单进入适配器前依次经过 KillSwitch、GuardChain 和 Wallet 审计。
- **从单一模型到多 Provider**：默认支持 Gemini，也可切换到 OpenAI、OpenRouter 或 Qwen 的 OpenAI 兼容接口。

## 核心能力

| 能力 | 说明 |
|:---|:---|
| 多源数据接入 | DataHub 封装 yfinance、腾讯行情、东方财富、Tushare、Tavily、Brave、RSS、OpenBB、opencli、bb-browser 等数据源，并提供本地缓存 |
| 标准化研究 | 17 个 Markdown 工作流定义市场发现、个股研究、交易审计、组合管理与复盘流程 |
| 报告契约与质量门 | 公共契约自动注入每个工作流；报告落盘前必须通过 `check_report_quality` 的结构、证据与冲突检查 |
| 跨族交叉验证 | 价格与财务指标按来源族判独立性，输出可直接抄进报告的证据判定与误差分档 |
| LLM 工具调用 | Gemini 自动函数调用；OpenAI 兼容 Provider 通过手动 tool loop 使用同一组 Python 工具 |
| 证据与产物 | ToolBus 管理工具预算与证据，结构化产物可写入报告和知识库 |
| 组合账本 | 基于 SQLite 的事件溯源账本使用 `Decimal` 计算，可通过事件回放重建持仓状态 |
| 主动触发 | 支持定时任务、价格异动和财报临近事件，并提供去重与冷却控制 |
| 多入口 | CLI 覆盖全部研究工作流；Telegram Bot 提供常用命令与定时任务入口 |
| 隐私隔离 | API Key、真实持仓、投资画像、报告和本地数据库默认由 `.gitignore` 排除 |

## 系统架构

AlphaSystem 使用 **Eyes – Brain – Memory** 三层架构，把“获取信息、形成判断、积累认知”拆成可替换的模块：

```text
CLI / Telegram Bot / Scheduler
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ Eyes · 感知层                                               │
│ DataHub + Cache                                              │
│ 行情 / 财务 / 搜索 / RSS / 公告 / 社交与浏览器数据          │
└──────────────────────────────┬──────────────────────────────┘
                               │ 标准化数据与证据
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Brain · 认知层                                               │
│ Workflow SOP + LLM Provider + ToolFactory / ToolBus          │
│ 研究编排 / 模型路由 / 工具调用 / 预算控制 / 证据追踪         │
└──────────────────────────────┬──────────────────────────────┘
                               │ 报告、知识与事件
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Memory · 记忆层                                              │
│ Reports / Knowledge Base / Portfolio Ledger / Event Log      │
│ 报告归档 / 知识卡片 / 持仓快照 / 可回放事件                 │
└─────────────────────────────────────────────────────────────┘
```

核心研究链路之外还有三个可选子系统：

- **执行管线**（`services/execution/`）：`KillSwitch → GuardChain → Wallet → Adapter → Ledger`。CLI 默认装配 `PaperAdapter`，实盘适配器需要额外配置与独立验证。
- **组合服务**（`services/portfolio/`）：SQLite 事件账本、CSV 导入、持仓快照与健康度计算。
- **触发引擎**（`services/trigger/`）：将定时、价格异动和财报临近事件路由到研究工作流，并执行去重、冷却和通知。

## 快速开始

### 1. 克隆仓库并创建虚拟环境

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/zx2592/Research.git
cd Research

python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell：

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

需要 bb-browser / Playwright MCP 集成时，再安装 Node.js 依赖：

```bash
npm install
```

部分旧版抓取器及其测试还会用到未包含在基础依赖中的可选包：

```bash
python -m pip install sec-edgar-downloader praw
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，选择一个 LLM Provider 并填写对应 Key。默认 Provider 是 Gemini：

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
TAVILY_API_KEY=your-tavily-api-key
```

`TAVILY_API_KEY` 用于依赖 Tavily 搜索的研究任务；若只使用其他数据源，可按工作流需要配置。Telegram、Brave、Tushare、RSSHub 等集成均为可选。

### 4. 准备个人配置（可选）

```bash
cp Config/holdings.example.json Config/holdings.json
cp Memory_Layer/Investment_Persona.example.md Memory_Layer/Investment_Persona.md
cp watchlist.json.example watchlist.json
```

这些真实文件已被 `.gitignore` 忽略。提交代码前仍应运行 `git status`，确认没有密钥、账户信息、持仓或研究报告进入暂存区。

### 5. 查看 CLI 并运行第一个工作流

```bash
python research_cli.py --help
python research_cli.py scan
python research_cli.py deep NVDA
```

> `--help` 中的命令摘要尚未覆盖完整 dispatch 表；下方“研究工作流”列出了当前代码实际支持的 17 个研究命令。

## 使用方式

### CLI

CLI 是覆盖最完整的入口。常用示例：

```bash
python research_cli.py scan
python research_cli.py deep NVDA
python research_cli.py quick TSLA "Robotaxi 发布会"
python research_cli.py verify "某公司将在下季度推出新产品"
python research_cli.py buy NVDA
python research_cli.py position
python research_cli.py optimize riskparity
```

CLI 还提供两个别名/辅助命令：

- `insight`：调用 `scan` 工作流生成市场洞察；
- `push [Ticker ...]`：运行纯 Python 信号推送，不启动 LLM。

### Telegram Bot

配置 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 后运行：

```bash
python bot/bot_service.py
```

Bot 当前注册常用研究命令，以及 `/morning`、`/earnings`、`/weekly` 等自动化任务入口。具体命令以 `bot/telegram_bot.py` 的 handler 注册表为准。

### 触发服务

```bash
python trigger_service.py
python trigger_service.py --poll-seconds 120
python trigger_service.py --disable-price
```

触发服务会把事件转换为工作流调用；是否发送 Telegram 通知取决于本地配置。

## 研究工作流

`research_cli.py` 当前 dispatch 表覆盖以下 17 个用户工作流。

### 市场发现

| 命令 | 参数 | 作用 |
|:---|:---|:---|
| `/scan` | — | 多源市场扫描，寻找主题收敛、异常与潜在线索 |
| `/lead` | `[关键词]` | 审计全球社交与市场情绪共振 |
| `/theme` | — | 发现 A 股主题方向并构建标的筛选逻辑 |
| `/core` | — | 刷新核心持仓并检查逻辑变化 |

### 个股研究

| 命令 | 参数 | 作用 |
|:---|:---|:---|
| `/deep` | `Ticker` | 商业模式、财务、估值、多空压力测试与监控清单 |
| `/value` | `Ticker` | 质量复利、护城河、文化与长期估值分析 |
| `/quick` | `Ticker + Event` | 对事件或异动进行快速影响评估 |
| `/update` | `Ticker` | 刷新公司财报、公告、新闻与投资逻辑 |
| `/verify` | `Claim` | 使用一手来源与交叉验证核查论断 |

### 交易决策

| 命令 | 参数 | 作用 |
|:---|:---|:---|
| `/buy` | `Ticker` | 买入前的逻辑、赔率、纪律和 FOMO 审计 |
| `/sell` | `Ticker` | 卖出信号、逻辑破缺与退出策略审计 |
| `/option` | `Ticker + 目标` | Covered Call、Cash-Secured Put、Protective Put 场景分析 |
| `/macro` | `[Event]` | 宏观事件对标的或组合的传导与压力测试 |

### 组合与复盘

| 命令 | 参数 | 作用 |
|:---|:---|:---|
| `/position` | — | 组合表现、集中度、相关性、研究新鲜度与再平衡体检 |
| `/optimize` | `[method]` | 以 maxdiv、minvol、maxsharpe 或 riskparity 生成优化建议 |
| `/rethink` | `[Ticker]` | 区分流程质量与运气，对交易进行复盘纠偏 |
| `/add` | — | 从最近研究中提取知识卡片并写入本地知识库 |

`/deep` 与 `/value` 在当前 CLI 路由中使用 Pro 模型（`ResearchAgent.PRO_WORKFLOWS`），其余研究工作流使用常规模型。模型名称可以通过环境变量覆盖。

## 研究质量保障

研究报告的价值取决于它能不能被复核。AlphaSystem 把这件事从"提示词里提醒一句"变成三层代码级约束。

### 1. 公共契约自动注入

`.agent/workflows/common/` 下的三份契约由 `WorkflowRunner` 拼接在每个工作流之前，无需在各工作流里重复：

| 契约 | 约束内容 |
|:---|:---|
| `00-report-contract.md` | 报告必备的八个章节、结论先行的一行判决、**价格证据行**、关键变化与数字底稿 |
| `10-evidence-contract.md` | T1–T4 来源分级、分市场的数据源优先级、来源族、误差分档、股价复权口径 |
| `20-quality-gate.md` | 出报告前的 8 问自检与印章、落盘前逐项复核表、历史报告冲突门禁 |

### 2. 落盘前的硬门禁

`write_to_file` 写入 `Reports/**/*.md` 时会先跑 `check_report_quality`：缺章节、无日期、无来源、只有单边观点、与同一标的的历史报告结论冲突却没有 `## 冲突解释`——任一条不过就拒绝写入并返回缺陷清单。

### 3. 跨族交叉验证

"取到两个数"不等于"交叉验证过"。腾讯财经、东方财富、新浪、同花顺、雪球都在转发同一份交易所行情，它们互相比对得到的 0.00% 偏差不是最高可信度，而是同一份数据比了两遍。

`cross_validate_price` 因此按**来源族**判独立性，`passed` 需同时满足三条：

1. 至少两个不同来源族给出数值（`intl-vendor` / `cn-exchange-relay` / `tw-vendor` / `primary-disclosure`）；
2. 跨族偏差在容差内；
3. 跨族数值不完全相同——两个真正独立的来源几乎不可能分毫不差。

未通过不是错误，是**未过项**：报告照常写，如实申报"单源未交叉"，但不得给出目标价、止损与盈亏比。工具返回的 `verdict` 是一句可以直接抄进结论区的话：

```text
价格证据：1502 · 2 源已交叉，偏差 0.13%（fetch_market_prices / tencent:qt.gtimg.cn，2026-08-23T07:31Z）
价格证据：153.7 · 单源未交叉（fetch_market_prices）——所有读数来自同一来源族，互相比对不构成交叉；本次不得给出目标价、止损与盈亏比
```

财务指标用 `cross_validate_metric` 走同一套逻辑，按 ≤1% ✅ / 1–5% ⚠️ / >5% ❌ 三档给结论；`verify_market_cap` 验算股价 × 总股本与披露市值的偏差，用来发现增发、回购、库存股与 ADR 存托比率带来的口径错配。

## 配置

完整模板见 [`.env.example`](.env.example)。配置值通过 `core/config.py` 读取，业务阈值集中在 `core/settings.py`。

### LLM Provider

| `LLM_PROVIDER` | Key | 默认常规模型 | 默认 Pro 模型 |
|:---|:---|:---|:---|
| `gemini` | `GEMINI_API_KEY` | `gemini-3-flash` | `gemini-3.1-pro` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | `gpt-4o` |
| `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` | `openai/gpt-4o` |
| `qwen` | `QWEN_API_KEY` 或 `DASHSCOPE_API_KEY` | `qwen-plus` | `qwen-max` |

Gemini 支持 `GEMINI_API_KEY_BACKUP` 回退。常规/Pro 模型分别可通过 Provider 对应的 `*_MODEL`、`*_MODEL_PRO` 变量覆盖；Gemini 使用 `VPS_MODEL` 和 `VPS_MODEL_PRO`。

OpenAI、OpenRouter 与 Qwen 共用 `core/llm_providers.py` 中的 OpenAI 兼容适配器，支持纯文本对话与函数调用。`TOOL_LOOP_MAX_ITERATIONS` 控制工具循环上限，默认值为 15。

### 数据源与可选集成

| 来源 | 主要用途 | 配置或依赖 |
|:---|:---|:---|
| yfinance | 多市场行情与财务数据 | `yfinance` |
| 腾讯行情 | A股 / 港股 / 美股实时快照，交叉验证的跨族第二来源 | 无需配置（零依赖直连） |
| 东方财富 | A股 52 周区间、估值指标与结构化年报财务 | 无需配置（零依赖直连） |
| Tushare | A 股行情、基本面与公告 | `TUSHARE_TOKEN` |
| Tavily | 研究型网页搜索 | `TAVILY_API_KEY` |
| Brave | 备用网页搜索 | `BRAVE_SEARCH_API_KEY` |
| RSS / RSSHub | 订阅与被动情报 | 可选 `RSSHUB_BASE` |
| OpenBB | 标准化金融数据 | OpenBB Python 包或本地服务 |
| opencli | 多站点命令行适配 | Node.js / 对应站点运行时 |
| bb-browser | 浏览器与社交数据 | Playwright MCP / 本地浏览器环境 |
| Kanzhiqiu | 社区摘要集成 | 本地 `integrations/kanzhiqiu/` 客户端 |

DataHub 的 source 模块定义了这些适配器；CLI 默认注册 bb-browser、opencli、yfinance、腾讯行情与东方财富，其余来源由脚本、ToolFactory 或调用方按需启用。腾讯行情与东方财富只用 stdlib（urllib 直连，失败回退 `curl --noproxy`），不需要 token。

## 项目结构

```text
Research/
├── .agent/workflows/       # 17 个用户工作流 + 共享时间上下文
│   └── common/             # 报告契约 / 证据契约 / 质量门（自动注入每个工作流）
├── core/                   # LLM、配置、工具、证据、产物与知识索引
│   ├── price_consensus.py  # 来源族判定、交叉验证分档、市值验算
│   └── report_quality.py   # 报告结构、证据与历史冲突校验
├── services/
│   ├── datahub/            # 数据源抽象、适配器与缓存
│   ├── execution/          # KillSwitch、GuardChain、Wallet 与执行适配器
│   ├── portfolio/          # 事件账本、快照、导入器与组合健康度
│   └── trigger/            # 事件模型、规则、去重、监控与执行
├── bot/                    # Telegram Bot 与守护服务
├── integrations/           # bb-browser、opencli、Kanzhiqiu 集成
├── scripts/                # 扫描、提醒、报告、优化与同步脚本
├── Memory_Layer/           # 投资画像模板、知识库与参考资料
├── Templates/              # 研究报告模板
├── tests/                  # pytest 测试
├── research_cli.py         # CLI 入口与工作流 dispatch
├── trigger_service.py      # 主动触发服务
└── requirements.txt        # Python 基础依赖
```

## 安全、隐私与执行边界

- **密钥**：`.env` 已被忽略；不要把任何 API Key 写进代码、示例、日志或报告。
- **个人数据**：真实持仓、投资画像、券商 CSV、报告、数据库和本地缓存默认不进入版本库。
- **路径保护**：模型写文件工具限制扩展名并执行安全路径解析，但仍应审查模型生成的每个产物。
- **证据边界**：工作流要求在数据不足时标注无法验证；LLM 输出仍可能包含错误，关键结论必须回到一手来源。
- **执行保护**：KillSwitch、仓位上限、冷却期和反向交易冷却是代码级防线，不是资金安全保证。
- **默认适配器**：CLI 当前装配 `PaperAdapter`。启用或开发实盘适配器前，请单独完成权限隔离、额度限制和券商沙盒测试。

## 测试

运行离线测试：

```bash
python -m pytest tests/ --ignore=tests/test_models.py
```

`tests/test_models.py` 是 Gemini 模型连通性脚本，会发起真实 API 请求，需要有效的 `GEMINI_API_KEY`：

```bash
GEMINI_API_KEY=your-key python tests/test_models.py
```

涉及旧版 SEC/Reddit 抓取器的测试还需要可选依赖：

```bash
python -m pip install sec-edgar-downloader praw
```

如果只修改核心模块，建议同时运行对应测试文件，例如：

```bash
python -m pytest tests/test_llm_client.py -v
python -m pytest tests/test_datahub.py -v
python -m pytest tests/test_portfolio_ledger.py -v
python -m pytest tests/test_execution.py -v
python -m pytest tests/test_trigger_engine.py -v
```

## 路线图

项目已具备完整研究工作流、事件账本、执行保护链和主动触发主干。后续方向以现有路线图文档为准：

- **Phase 7 · 主动智能**：继续完善异动监控、财报提醒、定时推送与事件反馈闭环。
- **Phase 8 · 深度增强**：加强行业关联、情景分析、组合风险与研究质量评估。
- **Phase 9 · Investment Copilot**：在严格审计与人工确认下，探索更完整的投资副驾驶体验。

详见 [Development_Roadmap_Summary.md](Development_Roadmap_Summary.md) 与 [next phase.md](https://github.com/zx2592/Research/blob/main/next%20phase.md)。路线图表达方向，不代表交付承诺。

## 贡献

欢迎提交问题报告、文档改进、数据源适配器、工作流优化和测试增强。

1. Fork 仓库并从 `main` 创建主题分支。
2. 将改动限制在一个清晰问题内，不要提交个人配置、密钥、报告或数据库。
3. 为行为变更补充或更新测试；文档改动需验证所有命令和相对链接。
4. 运行相关测试并在 Pull Request 中说明未运行的联网/凭证测试。
5. 提交 Pull Request，写明动机、实现边界、验证结果与潜在风险。

建议使用清晰的提交信息，例如：

```text
feat: add a market data source
fix: prevent duplicate trigger execution
docs: improve provider setup
test: cover portfolio event replay
```

在仓库补充正式许可证前，外部贡献的授权边界并不完整；维护者应优先明确许可证和贡献者条款。

## 文档

- [系统说明](SYSTEM.md) — 架构、命令体系、数据源与系统规则
- [命令手册](COMMANDS.md) — 工作流参数与调用示例
- [操作手册](System_Manual.md) — 更完整的安装、配置与运行说明
- [Phase 7 指南](Phase7_Guide.md) — 主动触发与自动化能力
- [macOS 部署指南](DEPLOY_MAC_V2.2.md) — macOS 环境部署参考
- [版本历史](CHANGELOG.md) — 版本演进与行为变化
- [演进路线图](Development_Roadmap_Summary.md) — Phase 7–9 规划

## 致谢

项目的方法论与架构受到以下公开项目启发：

- [OpenAlice](https://github.com/OpenAlice-AI/OpenAlice) — 多 Agent 异步协作与认知调度。
- [ValueCell](https://github.com/ValueCell) — 质量复利与自由现金流估值方法。
- [TIB-OS 3.0](https://github.com/Evan-XYZ/tib-os-3.0) — 趋势中军与题材量化框架。

---

如果 AlphaSystem 对你的研究流程有帮助，欢迎通过 Issue 或 Pull Request 分享使用反馈。
