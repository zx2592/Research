# 🦅 AI Investment Research System (AlphaSystem)

> **专家级 AI 投研工作台**
> 整合自动化数据采集、LLM 驱动的标准化投研工作流（17 个 Slash 命令）、以及事件溯源的组合账本与执行风控，构建一套可审计、可复用的量化辅助投研系统。

---

## 目录

- [核心理念](#核心理念)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [工作流命令大全（17 个）](#工作流命令大全17-个)
- [使用方式](#使用方式)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [安全与隐私](#安全与隐私)
- [鸣谢](#鸣谢)

---

## 核心理念

系统采用 **Eyes – Brain – Memory** 三层仿生架构，模拟人类研究员"看 → 想 → 记"的信息处理流程：

| 层 | 职责 | 实现 |
|:---|:---|:---|
| **Eyes（感知层）** | 统一数据采集与缓存 | `core/data_manager.py` + `services/datahub/`：yfinance、tushare、Tavily、Brave、RSS、opencli（80+ 站点适配器）、社交舆情抓取 |
| **Brain（认知层）** | LLM 处理与工作流编排 | `core/llm_client.py` + `.agent/workflows/`：双模式 LLM（桌面 IDE Agent / VPS google-genai），17 个工作流定义分析 SOP |
| **Memory（记忆层）** | 知识沉淀与归档 | `Memory_Layer/`、`Reports/`、`Config/`：知识卡片、按日/类型归档的报告、组合配置 |

**双模 LLM**：自动检测运行环境——桌面有 IDE CLI（claude/codex）走 desktop 模式；VPS/Bot 有 `GEMINI_API_KEY` 走 vps 模式。可用 `LLM_MODE` 强制覆盖。

**模型对齐**：`/deep` 与 `/value` 使用 **gemini-3.1-pro**（深度调研）；其余所有命令使用 **gemini-3-flash**（兼顾速度与成本）。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│            用户入口 (Entry Points)                          │
│   IDE 对话/命令  │  Telegram Bot  │  CLI (research_cli.py)  │
└──────────┬───────────────┬────────────────┬───────────────┘
           ▼               ▼                ▼
┌──────────────────────────────────────────────────────────┐
│  Eyes — 数据采集                                            │
│  RSS │ yfinance │ tushare │ Tavily │ Brave │ opencli │ 社交  │
│  (DataHub 统一缓存，避免重复 API 调用)                       │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Brain — LLM 处理                                           │
│  desktop: IDE Agent      │  vps: google-genai SDK          │
│  17 个 Workflow SOP  +  ToolBus 工具注册 + 证据追踪          │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Memory — 知识归档                                          │
│  Reports/ │ Knowledge_Base │ Config │ Obsidian (可选)       │
└──────────────────────────────────────────────────────────┘

附加子系统：
• 执行管线 services/execution/  → KillSwitch → GuardChain → Wallet → Adapter → Ledger
• 触发引擎 services/trigger/     → 价格异动 / 定时 / 财报临近 三类触发器
• 组合账本 services/portfolio/   → SQLite 事件溯源，状态由回放计算（Decimal 精度）
```

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r research/requirements.txt

# 2. 配置环境变量（在 research/ 下新建 .env）
#    必填: GEMINI_API_KEY, TAVILY_API_KEY
#    选填: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BRAVE_SEARCH_API_KEY, TUSHARE_TOKEN, RSSHUB_BASE

# 3. （可选）准备个人配置——从示例模板复制后填入自己的数据
cp research/Config/holdings.example.json research/Config/holdings.json
cp research/Memory_Layer/Investment_Persona.example.md research/Memory_Layer/Investment_Persona.md
#    ↑ 这两个真实文件已被 .gitignore 忽略，不会进入版本库

# 4. 运行 CLI
cd research
python research_cli.py scan          # 市场扫描
python research_cli.py deep NVDA     # 个股深度研究
```

> **关于个人数据**：本仓库**不包含**任何真实持仓或投资偏好。`holdings.json`、`Investment_Persona.md`、券商导出 CSV 等均被 `.gitignore` 忽略。仓库仅提供 `*.example` 脱敏模板，供你按格式自行填写。

---

## 工作流命令大全（17 个）

> 所有命令均可通过 **IDE 斜杠命令**（如 `/scan`）、**Telegram Bot** 或 **CLI**（`python research_cli.py scan`）触发。
> 报告归档规则：`/deep`、`/value` → `Reports/deepdive/`（深度沉淀）；其余 → `Reports/YYYYMMDD/`（按日归档）。
> 所有输出使用中文（简体），Ticker 等专有名词保留英文。

### 📡 市场发现类

| 命令 | 参数 | 模型 | 说明 |
|:---|:---|:---|:---|
| `/scan` | — | Flash | **市场全景扫描**：多源数据采集，识别四类信号（主题收敛 / 高影响异常 / 认知温差 / 深度基石），板块猎手深挖龙头与跨市场映射。 |
| `/lead` | [关键词?] | Flash | **市场领航者**：穿越雪球、Reddit 与专业研报的全球情绪共振审计，强制 ≥60% 新鲜外部线索，输出领航报告。 |
| `/theme` | — | Flash | **A股主题发现**：识别当前最强主题方向，构建逻辑链，筛选可交易标的。 |
| `/core` | — | Flash | **核心持仓简报**：实时刷新核心持仓（读取本地 `holdings.json`）的报价、异动与逻辑稳固度。 |

### 🔍 个股研究类

| 命令 | 参数 | 模型 | 说明 |
|:---|:---|:---|:---|
| `/deep` | Ticker | **Pro** | **个股深度研究**：三阶段——A) 商业模式+护城河+增长驱动 → B) 财务深度+盈利预测+动态PE+反向DCF → C) 多空压力测试+致命风险清单。 |
| `/value` | Ticker | **Pro** | **质量复利分析**：Buffett / 李录 / 段永平 / 达尔文框架——10 年财务、护城河深度、企业文化、估值锚点，评估长期持有价值。 |
| `/quick` | Ticker + Event | Flash | **事件快评**：信息分级（Class A/B）+ 边际变化（What/Why/Impact）+ 玩家扫描 + 长短双轨策略。 |
| `/update` | Ticker | Flash | **公司情报刷新**：拉取最新财报/新闻/公告，校验投资逻辑，更新估值锚点。 |
| `/verify` | Claim | Flash | **事实核查**：对传闻或论断做一手源搜索与交叉验证，给出 Confirmed / Falsified / Unverified 判决。 |

### 🛒 交易决策类

| 命令 | 参数 | 模型 | 说明 |
|:---|:---|:---|:---|
| `/buy` | Ticker | Flash | **买入审计**：板块Beta熔断 + 股性Checklist + 策略定位 + 止损/目标/盈亏比 + 纪律合规 + FOMO 自检 → 🟢通过/🟡观望/🔴驳回。 |
| `/sell` | Ticker | Flash | **卖出审计**：入场定性回溯 + 风格漂移检查 + 5 类卖出信号 + 4 种策略选项（止损/MoonBag/备兑/持有）+ 漂移自检。 |
| `/option` | Ticker + 目标 | Flash | **期权策略**：Covered Call / Cash Secured Put / Protective Put 三场景，计算行权价、Delta、年化收益与盈亏场景。 |
| `/macro` | Event | Flash | **宏观压力测试**：宏观事件对持仓/个股的冲击评估（贴现率敏感度 + 业务传导 + 避险属性），输出传导链与操作建议。 |

### 📊 组合管理类

| 命令 | 参数 | 模型 | 说明 |
|:---|:---|:---|:---|
| `/position` | — | Flash | **持仓体检**：量化绩效仪表盘（Sharpe/回撤/CAGR vs SPY）+ 收益归因 + 研究新鲜度 + 相关性矩阵 + 集中度风险 + 再平衡建议 + HTML Tearsheet。 |
| `/optimize` | [method?] | Flash | **组合优化**：计算最优权重（maxdiv/minvol/maxsharpe/riskparity），生成具体调仓清单，含风控校验与定性审视。 |

### 🔁 复盘 / 知识类

| 命令 | 参数 | 模型 | 说明 |
|:---|:---|:---|:---|
| `/rethink` | Ticker | Flash | **交易复盘**：知行合一检查 + 运气vs实力区分 + SOP 漏洞诊断 → 0–10 纪律评分 + 核心教训 + 改进动作。 |
| `/add` | — | Flash | **知识库留存**：提取当前研报核心洞察，生成知识卡片存入 `Memory_Layer/Knowledge_Base/`，可选同步 Obsidian。 |

---

## 使用方式

三种入口，能力一致：

| 入口 | 示例 |
|:---|:---|
| **IDE 对话/命令** | 直接输入 `/scan`、`/deep NVDA`、`/buy NVDA` |
| **Telegram Bot** | 向 Bot 发送 `/scan`、`/position` 等命令 |
| **命令行 CLI** | `python research_cli.py scan` / `deep NVDA` / `quick TSLA "Robotaxi 发布会"` |

```bash
# CLI 用法示例（在 research/ 目录下）
python research_cli.py scan                    # 市场扫描
python research_cli.py deep NVDA               # 深度研究
python research_cli.py quick TSLA "财报超预期"  # 事件快评
python research_cli.py value MCO               # 质量复利分析
python research_cli.py buy NVDA                # 买入审计
python research_cli.py sell NVDA               # 卖出审计
python research_cli.py position                # 持仓体检
python research_cli.py --llm-mode vps scan     # 强制 VPS 模式
```

### 后台服务

```bash
python research/trigger_service.py                    # 触发引擎（默认 60s 轮询）
python research/trigger_service.py --poll-seconds 120 # 自定义间隔
python research/trigger_service.py --disable-price    # 关闭价格触发
python research/bot/bot_service.py                    # Telegram Bot（自动重启）
```

### 运行测试

```bash
cd research
python -m pytest tests/                         # 全部测试
python -m pytest tests/test_portfolio_ledger.py # 单个文件
python -m pytest tests/test_execution.py -v     # 详细输出
```

---

## 配置说明

`.env`（位于 `research/`）：

| 变量 | 必填 | 说明 |
|:---|:---:|:---|
| `GEMINI_API_KEY` | ✅ | VPS 模式 LLM |
| `TAVILY_API_KEY` | ✅ | 主力搜索引擎 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | | Telegram Bot |
| `BRAVE_SEARCH_API_KEY` | | 备用搜索 |
| `TUSHARE_TOKEN` | | A 股基本面/公告 |
| `RSSHUB_BASE` | | 自建 RSSHub 地址 |
| `LLM_MODE` | | `auto`（默认）/ `desktop` / `vps` |
| `VPS_MODEL` / `VPS_MODEL_PRO` | | 覆盖默认 Flash / Pro 模型名 |

个人数据文件（**均被 `.gitignore` 忽略**，仓库仅含 `*.example` 模板）：

| 文件 | 模板 | 用途 |
|:---|:---|:---|
| `Config/holdings.json` | `Config/holdings.example.json` | 持仓明细（通常由 `parse_positions.py` 从券商导出生成） |
| `Memory_Layer/Investment_Persona.md` | `Memory_Layer/Investment_Persona.example.md` | 个人投资框架与偏好 |

---

## 项目结构

```text
research/
├── core/            # 核心模块：LLM 客户端、DataHub、ToolBus、配置中心、知识库
├── services/        # 子系统：datahub / execution / portfolio / trigger
├── bot/             # Telegram Bot 交互层
├── integrations/    # bb-browser（社交抓取）、opencli（站点适配器）
├── .agent/workflows/# 17 个工作流 SOP（Prompt 定义）
├── Config/          # 配置（真实个人数据被忽略，仅留 *.example）
├── Memory_Layer/    # 知识库、写作风格参考、工作流规则
├── Reports/         # 研究报告归档（被忽略）
├── Templates/       # 报告模板
├── tests/           # pytest 测试套件
└── research_cli.py  # CLI 指挥中枢（WorkflowRunner）
```

---

## 安全与隐私

- **零幻觉原则**：原始数据不足时必须明确标注"无法验证"，严禁捏造财务或持仓数据。
- **个人数据隔离**：`.gitignore` 过滤所有真实持仓、投资偏好、券商导出、报告与本地配置；仓库仅含脱敏 `*.example` 模板。
- **执行风控**：实盘前经过 KillSwitch → GuardChain（仓位上限 15% / 24h 冷却 / 反向 30d 冷却）→ Wallet 审计 → Adapter → Ledger 结算。
- **历史卫生**：推送前须扫描全部 git 历史中的密钥与个人数据（`git log -p | grep -iE '(api_key|secret|token|password|sk-|账户号)'`）。

---

## 鸣谢

本项目在架构与方法论上参考借鉴了以下优秀的公开项目，特此鸣谢：

- **[OpenAlice](https://github.com/OpenAlice-AI/OpenAlice)** — 多 Agent 异步投研协作架构与认知层调度的参考。
- **[ValueCell](https://github.com/ValueCell)** — "质量复利"与"自由现金流贴现"方法论的启发。
- **[TIB-OS 3.0](https://github.com/Evan-XYZ/tib-os-3.0)** — "趋势中军"方法论与多维题材量化打分逻辑的架构启发。
