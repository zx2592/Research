一、Phase 7 的正确定位

你文档里对 Phase 7 的定义非常准确：

7.1 异动扫雷快评（Sentinel）已并入 /scan

7.2 财报日历提醒

7.3 晨报自动推送

7.4 持仓日报/周报

也就是说，Phase 7 不是新增研究能力，而是给现有 workflow 增加主动触发层。

20260305_SystemInsights

结合你现有架构，最合理的做法是：

在 V3 核心模块之上，新加一个 Trigger Engine。

它不替代 /scan /quick /radar /position，只负责回答两个问题：

什么时候该触发

触发后该调用哪个现有 workflow

你现有工作流、数据源、Bot、Market Sentinel、绝对规则都已经成型，所以 Trigger Engine 本质上是“调度与路由层”，不是分析层。

SYSTEM

 

SYSTEM

二、目标架构

建议新增一层：

Entry Points / Bot / CLI
        │
        ▼
  Trigger Engine   ← 新增
        │
        ├── /scan
        ├── /quick
        ├── /radar
        └── /position
        │
        ▼
EventLog / ToolBus / DataHub / KnowledgeHub / PortfolioLedger / ExecutionGateway

你的现状已经有：

Market Sentinel

Telegram Bot

Bot Service

16 个 workflow 命令体系

DataHub / Ledger / EventLog / ToolBus 等内核模块 

SYSTEM

 

20260305_SystemInsights

所以 Trigger Engine 只需要补齐 5 件事：

事件采集

规则判断

调度去重

workflow 路由

推送与审计

三、核心设计原则
1) 只触发现有 workflow

不要在 Trigger Engine 里写分析逻辑。
它只负责：

生成 /quick NVDA

生成 /radar SPGI

生成 /scan

生成 /position

这样可以最大化复用你现在的 .agent/workflows/*.md 体系。

SYSTEM

2) 事件必须先标准化，再判断

价格异动、财报日历、新闻命中、持仓变化，都先转成统一事件对象。
否则后面规则会越来越乱。

3) 幂等优先

同一个事件不能重复触发多次推送。
尤其是：

webhook 重试

同一新闻多源重复

价格多次轮询命中同一阈值

4) 触发和执行分离

Trigger Engine 只负责“决定要不要跑”；真正跑 workflow 还是走你现有 CLI/Bot/Agent 入口。

5) 全部落 EventLog

你既然已经有 EventLog，就应该把 Trigger 的每一步都事件化：发现、判定、排队、执行、推送、失败。

20260305_SystemInsights

四、事件模型设计

建议定义统一事件对象 TriggerEvent：

{
  "event_id": "evt_20260306_abc123",
  "event_type": "price_move|earnings_upcoming|news_hit|portfolio_change|schedule_tick",
  "source": "sentinel|calendar|rss|broker|cron",
  "symbol": "NVDA",
  "portfolio_scope": "core|watchlist|holding|all",
  "occurred_at": "2026-03-06T07:58:00-08:00",
  "asof_date": "2026-03-06",
  "payload": {},
  "dedupe_key": "price_move:NVDA:2026-03-06:open_session",
  "severity": "info|medium|high|critical"
}
必备字段解释

event_type

price_move

earnings_upcoming

news_hit

portfolio_change

schedule_tick

portfolio_scope

holding：当前持仓

core：核心关注池

watchlist：观察池

all：全市场任务

dedupe_key

用来防止重复推送

例如同一只票在同一交易时段超过 4% 只推一次

五、规则引擎设计

建议不要一开始做复杂 DSL。
第一版就用 Python 规则类 + YAML 配置。

规则对象
class TriggerRule:
    rule_id: str
    enabled: bool
    event_type: str
    predicate(event, context) -> bool
    action(event, context) -> WorkflowInvocation
    cooldown_minutes: int
    priority: int
WorkflowInvocation
{
  "workflow": "/quick",
  "args": ["NVDA"],
  "reason": "盘中涨跌幅超过4%",
  "delivery": ["telegram"],
  "artifact_tag": "sentinel_quick"
}
六、Phase 7 的四类规则
Rule A：异动快评

你的 7.1 已经把 Sentinel 并入 /scan，即在生成扫描报告时自动识别核心资产涨跌幅 >4%。

20260305_SystemInsights

下一步建议补两个模式：

A1. 扫描内嵌模式

继续保留现在的 /scan 内嵌快评

用于晨报和日常全景扫描

A2. 独立告警模式

交易时段内，如果核心持仓或 watchlist 涨跌幅超过阈值

直接触发 /quick SYMBOL

推送 Telegram 精简版

建议阈值

持仓：abs(change_pct) >= 3.5%

核心观察池：abs(change_pct) >= 4.0%

非核心：忽略

冷却策略

单 symbol 每个交易时段最多推 1 次

如果从 medium 升级到 critical 可再次推送

输出

Telegram：3 行精简版

文件：完整 Markdown 落盘，符合你“每个命令必须生成 Markdown”的规则 

SYSTEM

Rule B：财报日历提醒

这就是你 Phase 7 的 7.2。文档定义为：每周日自动扫描持仓中下一周有财报的标的，提前生成 /radar 并推送。

20260305_SystemInsights

调度

每周日 18:00，America/Los_Angeles

输入

PortfolioLedger 当前持仓

Core universe 可选

Earnings calendar 数据源

规则

若标的在未来 7 天内有财报

触发 /radar SYMBOL

为什么用 /radar 而不是 /quick

因为财报前提醒不是突发事件，而是预检。
/radar 更适合做：

市场预期

历史财报反应

本次看点

风险点

相关持仓联动

推送结构

建议不是一条一条推，而是：

一条周总览

附带 1~N 只个股 radar 报告链接/摘要

Rule C：晨报自动推送

这是 7.3。文档定义为每个交易日早 8:00 自动执行 /scan 并推送精简版到 Telegram。

20260305_SystemInsights

调度

每个交易日 08:00，America/Los_Angeles

行为

生成 /scan

产出完整 Markdown

Telegram 发送精简摘要

建议摘要格式
【晨报 | 2026-03-06】
1. 隔夜最重要：...
2. 核心持仓异动：...
3. 今日财报/宏观关注：...
4. 风险提醒：...
5. 建议查看：完整 /scan 报告
关键点

不要在 Telegram 里塞完整内容

只发“你今天是否值得点开完整报告”的摘要

Rule D：持仓日报/周报

这是 7.4。文档定义为每周末自动执行 /position，生成组合健康度、本周盈亏总结、风控预警并推送。

20260305_SystemInsights

我建议分成两个级别：

D1. 日报

每个交易日收盘后 17:30

触发 /position

输出：

NAV 变化

当日贡献前三/拖累前三

风险预警

D2. 周报

每周六 09:00

触发 /position

输出：

周收益、月收益、YTD

仓位变化

集中度变化

本周执行的买卖回顾

下周风险点

七、上下文装配器：Trigger 不是只传 ticker

为了让自动触发出来的报告更有用，建议在触发前给 workflow 自动注入上下文。

对 /quick

注入：

当前持仓状态

最近 7 天相关新闻摘要

最近 3 份相关报告

价格异动原因候选

对 /radar

注入：

财报日期

历史 4 次财报前后表现

当前仓位

同行业关联持仓

对 /position

注入：

Ledger snapshot

最新成交与现金变化

风险矩阵

这一步可以直接复用你已经有的：

PortfolioLedger

KnowledgeHub

DataHub

ToolBus/Evidence 体系 

20260305_SystemInsights

八、数据库表设计

既然你已有 SQLite 事件溯源与组合数据库，Phase 7 建议最少补 4 张表。

20260305_SystemInsights

1) trigger_events

原始标准化事件表

CREATE TABLE trigger_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  symbol TEXT,
  portfolio_scope TEXT,
  occurred_at TEXT NOT NULL,
  asof_date TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  severity TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_trigger_events_type_time ON trigger_events(event_type, occurred_at);
CREATE INDEX idx_trigger_events_symbol_time ON trigger_events(symbol, occurred_at);
2) trigger_rules

规则配置表

CREATE TABLE trigger_rules (
  rule_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  config_json TEXT NOT NULL,
  cooldown_minutes INTEGER NOT NULL,
  priority INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
3) trigger_jobs

规则命中后的待执行任务

CREATE TABLE trigger_jobs (
  job_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  workflow TEXT NOT NULL,
  args_json TEXT NOT NULL,
  status TEXT NOT NULL,      -- queued/running/succeeded/failed/skipped
  reason TEXT NOT NULL,
  artifact_path TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX idx_trigger_jobs_status_created ON trigger_jobs(status, created_at);
4) trigger_deliveries

推送与发送结果

CREATE TABLE trigger_deliveries (
  delivery_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  channel TEXT NOT NULL,     -- telegram/cli/log
  status TEXT NOT NULL,      -- pending/sent/failed
  message_hash TEXT,
  sent_at TEXT,
  error_text TEXT
);
九、去重、节流、冷却

这是 Trigger Engine 里最容易后面出问题的地方。

1) 去重键

建议按事件类型定义：

价格异动

price_move:{symbol}:{trade_date}:{session}

财报提醒

earnings_upcoming:{symbol}:{earnings_date}

晨报

scan_morning:{trade_date}

周报

position_weekly:{week_ending}

2) 节流

Telegram 推送要有总量限制，例如：

单小时不超过 5 条主动快评

超过后合并为 digest

3) 优先级

优先级从高到低：

持仓相关 critical 风险

财报前提醒

晨报

watchlist 异动

十、工作流路由实现

建议新增一个独立服务或模块：

services/trigger_engine/

建议拆成这些文件：

services/trigger_engine/
├── engine.py          # 主循环/调度器
├── events.py          # 事件标准化
├── rules.py           # 规则定义
├── scheduler.py       # cron 触发
├── dispatcher.py      # workflow 调用
├── dedupe.py          # 去重冷却
├── delivery.py        # Telegram 推送
└── repository.py      # SQLite 读写
Dispatcher 职责

它只做一件事：把 trigger_job 转成真实 workflow 调用。

例如：

dispatch("/quick", ["NVDA"])
dispatch("/scan", [])
dispatch("/position", [])
dispatch("/radar", ["SPGI"])

不要在这里重复实现 workflow 逻辑。

十一、与现有 ToolBus 的关系

你已经有 ToolBus，且包含 Registry + Budget + Evidence。

20260305_SystemInsights

Phase 7 里建议这样用：

1) Trigger Engine 不直接调用搜索

Trigger Engine 只触发 workflow。
真正搜索仍在 workflow 内部进行。

2) 预算继承

自动触发的 /scan /quick /radar 也必须受 8 次搜索预算约束。你系统的绝对规则里已经写明每任务最多 8 次搜索调用。

SYSTEM

3) Evidence 继续由 workflow 记录

不要在 Trigger Engine 再做一套引用系统。

十二、与 EventLog 的关系

EventLog 已生产就绪，所以 Phase 7 每一步都应该写事件。

20260305_SystemInsights

建议至少新增这些 event types：

trigger.event_ingested

trigger.rule_matched

trigger.job_queued

trigger.job_started

trigger.job_succeeded

trigger.job_failed

trigger.delivery_sent

trigger.delivery_failed

这样以后你排错会非常轻松：
“为什么今天晨报没发？”
你可以直接沿着事件链查。

十三、最小可上线版本

我建议你不要一次把 7.2/7.3/7.4 全做满。
按这个顺序上线最稳：

第一步：晨报自动推送

原因：

最简单

风险最低

体感最明显

只依赖 /scan

第二步：财报日历提醒

原因：

业务价值高

规则清楚

/radar 已存在

第三步：持仓周报

原因：

组合层价值高

但要确保 /position 已完全读 Ledger，而不是旧静态文件
你前文也指出 /position 过去有“未接 Ledger 实时数据”的缺口，后续已被 Phase 6 规划解决。

20260305_SystemInsights

 

20260305_SystemInsights

第四步：盘中异动主动快评

原因：

噪音最多

去重节流最复杂

应该最后做

十四、推荐的具体时间表
Week 1

完成：

trigger_events

trigger_jobs

scheduler

dispatcher

晨报自动 /scan

验收标准：

每个交易日 08:00 自动生成完整 /scan

Telegram 收到摘要

EventLog 可完整追踪

Week 2

完成：

财报日历数据接入

earnings_upcoming 规则

/radar 自动推送

验收标准：

周日自动生成下一周持仓财报清单

同一只票不重复推送

Week 3

完成：

/position 日报/周报自动化

delivery digest 模式

验收标准：

周报可总结 NAV、仓位变化、风控提醒

文件与 Telegram 摘要一致

Week 4

完成：

盘中 price_move 事件

阈值去重

交易时段冷却

验收标准：

持仓异动只推一次

同时保留完整 /quick 报告落盘

十五、几个非常具体的工程建议
1) 统一时区

你系统已经强调要自动注入时区上下文，避免“未来日期”错误。

20260305_SystemInsights


Phase 7 里所有调度都统一使用：

存储：UTC

展示与调度：America/Los_Angeles

2) 文件命名规范

自动触发生成的 Markdown 建议单独加 tag：

Reports/YYYYMMDD/
  20260306_scan_morning.md
  20260306_quick_NVDA_sentinel.md
  20260309_radar_SPGI_earnings.md
  20260314_position_weekly.md

这样方便后续 KnowledgeHub 自动吸收。

3) Telegram 只发摘要

不要发全量报告。
否则你很快会对主动通知失去耐心。

4) 失败降级

如果 workflow 执行失败：

记录 trigger.job_failed

Telegram 发一条极简失败通知

不要无限重试

5) Break-glass

如果 Trigger Engine 某条规则在短时间内连续失败：

自动禁用该规则

避免消息风暴

十六、我认为你最该先写的三个类

如果只从代码开工角度说，先写这三个：

TriggerEventFactory

负责把：

cron

sentinel

earnings calendar

broker/ledger变化

统一转成标准事件。

RuleEvaluator

输入事件，输出 0~N 个 WorkflowInvocation。

WorkflowDispatcher

把 invocation 交给你现有 CLI/Bot/workflow runner。

只要这三个类跑通，Phase 7 的主干就立住了。

十七、最后给你的结论

一句话概括这版设计：

Phase 7 不是“再加智能”，而是把你已经做好的 /scan /quick /radar /position 变成可被事件主动调用的服务。

也就是说：

V3 内核继续不动

workflow 继续不动

Trigger Engine 作为薄薄的一层加上去

先做晨报，再做财报提醒，再做周报，最后做盘中主动快评

这条路线最稳，也最符合你现在系统“功能已够，缺统一控制面”的状态。

20260305_SystemInsights

 

20260305_SystemInsights

下一条我可以继续直接给你：
1）SQLite DDL 完整版，或者 2）services/trigger_engine/ 的 Python 文件骨架。