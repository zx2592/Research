# CHANGELOG — AI 投资研究系统版本历史

> 本文件记录系统各版本的功能演进、架构变化与 Bug 修正。
> 最新版本在上，历史版本在下。

---

## [V4.2] — 2026-06-03

> **主题：多 Provider 接入 — OpenAI / OpenRouter / Qwen（含工具循环）(Multi-Provider with Tool Loop)**
>
> V4.2 在保持 Gemini 为默认实现的前提下，新增了 OpenAI 兼容接口支持。三家（OpenAI、OpenRouter、Qwen/DashScope）均为 OpenAI 兼容协议，共用一个适配器，仅 base_url / key / model 不同。**纯文本对话与工具调用（function calling）均已实现**——工具调用通过手动 JSON-schema 工具循环驱动，标准工作流（scan/deep/buy/...）可直接运行在这三家上。

### 新增 Provider 模块
- **新建** `core/llm_providers.py`：
  - `resolve_provider()`：读取 `LLM_PROVIDER`（默认 `gemini`），大小写/空白容错
  - `OPENAI_COMPATIBLE_PROVIDERS` 配置表：openai / openrouter / qwen 的 base_url、key 环境变量、默认模型
  - `build_openai_tools()`：将 Python 可调用对象（ToolFactory 工具）转换为 OpenAI JSON-schema 工具定义 + name→callable 映射；自动跳过 `*args`/`**kwargs`，无默认值的参数标记为 required，无注解默认 string
  - `OpenAICompatibleProvider`：懒加载 openai SDK，实现 `create_session` / `chat` / `reset`，含 `_run_tool_loop()`（请求 → tool_calls → 执行 → 回填结果 → 循环，复用 `settings.tool_loop.max_iterations`，达上限强制收尾）
- **改造** `core/llm_client.py`：`__init__` 按 `provider` 路由——`gemini` 走原 google-genai 路径，其余走 `_init_openai_compatible()`；`create_chat` / `chat` / `reset` 增加 provider 分发

### Provider 配置（均可经环境变量覆盖）
| Provider | base_url | Key 环境变量 | 默认模型（free / pro）|
|:---|:---|:---|:---|
| openai | SDK 默认 | `OPENAI_API_KEY` | `gpt-4o-mini` / `gpt-4o` |
| openrouter | `openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` / `openai/gpt-4o` |
| qwen | `dashscope.aliyuncs.com/compatible-mode/v1` | `QWEN_API_KEY` / `DASHSCOPE_API_KEY` | `qwen-plus` / `qwen-max` |

### 工具循环要点
- 工具复用 Gemini 同款 Python 可调用对象（ToolFactory），无需为各 Provider 重复定义
- 未知工具名、参数 JSON 解析失败、工具执行抛异常 → 均以 `Error: ...` 文本回填，循环可自愈继续
- 达到最大迭代轮数 → 记 warning 并发起一次无工具的收尾请求提取最终摘要

### 边界说明
- Gemini 为默认值，现有行为完全不变；切换 Provider 仅需设 `LLM_PROVIDER` + 对应 Key
- OpenAI 兼容接口需安装 `openai` SDK（已在 requirements.txt）

### 文档同步
- `README.md`：新增"LLM Provider"环境变量小节；`SYSTEM.md` 第 3 节补多 Provider 说明

### 测试
- **新建** `tests/test_llm_providers.py`（21 项）：provider 解析、配置表、缺 Key 报错、模型默认/覆盖、Qwen 双 Key 回退、`build_openai_tools` schema 生成（变参跳过/required/无注解默认）、纯文本往返、reset、工具循环（执行+回填+收尾、未知工具、工具异常、最大迭代）、LLMClient provider 路由与工具循环
- `tests/test_llm_client.py`：`_make_vps_client` 补 `provider="gemini"` 兼容新分发
- 全量测试 **344 passed, 1 skipped**

---

## [V4.1] — 2026-06-03

> **主题：架构精简 — 移除桌面 IDE 模式与触发器排队旁路 (API-Only Simplification)**
>
> V4.1 将系统的执行路径统一为纯 API 驱动。删除了为本地 IDE 环境设计的桌面模式（通过 claude/codex 子进程驱动）及其配套的触发器收件箱排队子系统。LLM 调用与触发器执行现在一律直连 Gemini API，结构更简单、行为更一致，同时清除了一批零消费者的死代码。

### 移除桌面 LLM 模式（概念 A）
- **删除** `core/ide_providers.py`（~625 行 IDE 子进程抽象层：ClaudeCode / Codex / GeminiADC 三个 Provider）
- **重写** `core/llm_client.py`：移除 `_detect_mode` / `_init_desktop` / `_chat_desktop` 等全部 desktop 分支，`LLMClient` 恒走 google-genai SDK（保留主/备 Key 有序回退）。`LLMClient.__init__` 的 `force_mode` 参数彻底移除
- `research_cli.py`：`ResearchAgent.__init__` 的 `llm_mode` 参数与 `--llm-mode` CLI 选项彻底移除

### 移除触发器 desktop 排队旁路（概念 B）
- **删除** `services/trigger/inbox.py`（402 行收件箱状态机）与 `services/trigger/ide_dialog_inbox.py`（393 行中文对话外壳，生产端零消费者）
- **简化** `services/trigger/executor.py`：删除 `DesktopQueueWorkflowExecutor`，`build_workflow_executor()` 恒返回 `ResearchWorkflowExecutor`（API 直跑）
- **简化** `services/trigger/monitor.py`：移除 `ide_inbox` 与 `executor_mode` 参数及排队渲染分支
- `trigger_service.py` / `trigger_runner.py`：`--executor` CLI 选项彻底移除；`build_workflow_executor()` / `build_monitor_engine()` 不再接受 `mode` 参数

### ⚠️ 行为变更
- 触发器（定时 / 价格异动 / 财报临近）在**所有平台**统一直接调用 API 执行 workflow，不再于 Windows 上排队等待人工处理。后台 `trigger_service.py` 命中触发条件即真实消耗 token 并自动写报告

### 文档同步
- `SYSTEM.md` / `README.md`：架构图与模式说明由"双模式"更新为"API 驱动单模式"

### 测试
- 删除 `tests/test_ide_providers.py` 与 `tests/test_trigger_inbox_dialog.py`
- 精简 `tests/test_llm_client.py`、`tests/test_model_routing.py`、`tests/test_trigger_engine.py`、`tests/test_concurrency.py` 中的 desktop / inbox 相关用例
- `tests/test_trigger_monitor.py` 重写为 API 直跑路径验证
- 全量测试 **323 passed, 1 skipped**

---

## [V3.88] — 2026-04-03

> **主题：浏览器自主化与核心持仓扫描 (Browser Autonomy & Core Pulse)**
>
> V3.88 是感知层的重大里程碑，通过集成 opencli v1.6.1，系统不再局限于解析静态数据，而是具备了真实的网页交互与自主学习能力。同时，新增了对核心标的的零延时逻辑审计。

### 核心升级
#### 🚀 opencli v1.6.1 深度融合
- **[EYES-1] browser_operate 工具**: Agent 现在可以使用 `open`, `click`, `type`, `screenshot`, `scroll` 等指令。支持对冷门/非标准站点的自主数据抓取。
- **[EYES-2] learn_source 自动适配**: 引入 `opencli generate` 能力。遇到新站点时，系统可发起自主探索并自动生成 YAML 抓取适配器。
- **[EYES-3] system_doctor 自诊**: 接入连通性自动检查，实时监控 Browser Bridge 插件与 daemon 状态。

#### 📈 /core 核心持仓工作流
- **[WF-CORE] 核心持仓监控**: 运行时读取本地 `Config/holdings.json` 中的核心标的清单，逐一刷新行情与逻辑。
- **[WF-CORE] 逻辑异动审计**: 每日一键刷新行情，自动对比最新财报/新闻与历史基准逻辑的差异（Marginal Change）。

#### 🧹 系统瘦身与清理
- **[SYS-1] 屏蔽 kanzhiqiu**: 彻底删除相关代码与工具定义，收敛情报源至更可控的社交媒体与全球新闻。
- **[SYS-2] 光通讯逻辑更新**: 重构算力基建研究框架，引入“毛细血管”爆发逻辑。

---

## [V3.8] — 2026-04-01

> **主题：趋势中军方法论与模型调度标准化 (Trend Core & Model Standards)**
>
> V3.8 确立了系统的投资哲学，并针对 Gemini 系列模型进行了严格的工作流对齐，确保深度分析与快速审计各展所长。

### 核心升级
- **[PHIL-1] 趋势中军 (Trend Core)**: 建立了一套包含题材持续性、个股质地与仓位管理的量化评分体系。
- **[LLM-1] 模型调度标准**: 强制 `/deep` / `/value` 使用 Pro 模型；`/buy` / `/sell` 等高速任务使用 Flash 模型。
- **[SYS-1] I/O 效率优化**: 自动清理残留线程与过期缓存，解决大规模抓取时的系统夯住问题。

---

## [V3.6] — 2026-03-18

> **主题：Trigger Engine 稳定性修复与生产加固 (Trigger Hardening)**
>
> V3.6 修复了 Trigger Engine 在生产环境中暴露的三个关键问题，确保价格异动监控、财报日历提醒和定时调度全部可靠运行。

### Bug 修复（3 项）

#### 🔧 yfinance API 兼容性修复
- **[FIX-1] `_get_earnings_date` 适配 dict 格式**: 新版 yfinance 的 `ticker.calendar` 返回 `dict` 而非 DataFrame，旧代码用 `.columns`/`.index` 取值失败导致所有财报日期返回 None。新增 `dict` 分支处理 + `datetime.date→datetime` 类型转换。

#### 🔧 Trigger Executor 模式解析修复
- **[FIX-2] `build_workflow_executor` auto 模式死循环**: `.env` 中 `LLM_MODE=auto` 时，executor 解析链 `auto→LLM_MODE→"auto"` 循环未终止，直接抛 `ValueError`。修复为二次解析：Windows 默认 `desktop`，Linux 默认 `vps`。

#### 🔧 缓存中毒清理
- **[FIX-3] 失效代理导致 27 条空缓存**: 本机代理（127.0.0.1:9）离线后，yfinance 全部请求失败，空结果被 `DataCache` 缓存 24h，阻塞后续所有 earnings 查询。清理 `data/cache/` 中 27 条 `earnings_date=""` 的缓存条目，并删除残留的 `trigger_service.pid`。

### 质量保障
- 全部 30 个 Trigger 相关测试通过 ✅
- 三类 Provider 实测验证：PriceMoveProvider（CANG 异动触发 /quick）、ScheduleProvider（晨扫 7:30 正常路由）、EarningsUpcomingProvider（查询正常，当前无 7 天窗口内财报）

---

## [V3.5] 鈥?2026-03-17

> **涓婚锛氱ぞ浜ゆ櫤鑳戒笌鍏ㄧ悆鎯呯华鍏辨尟 (Social Intelligence & Global Sentiment)**
>
> V3.5 寮曞叆浜嗗熀浜?`bb-browser` 鐨勭涓夋柟娴忚鍣ㄧ姸鎬侀泦鎴愭柟妗堬紝褰诲簳鎵撶牬浜嗕紶缁?API 鐨勬暟鎹宀涖€傜郴缁熺幇鍦ㄥ彲浠ュ埄鐢ㄦ湰鍦版祻瑙堝櫒鐨勭櫥褰曟€侊紝瀹炴椂鎶撳彇闆悆銆丷eddit 绛夌ぞ浜よ储缁忕ぞ鍖虹殑娣卞害鎯呯华锛屽苟鏂板浜?`/lead` 宸ヤ綔娴佺敤浜庤嚜鍔ㄥ寲鍏ㄧ綉璋冪爺銆?

### 鏍稿績鍗囩骇锛? 椤癸級

#### 馃寪 `bb-browser` 娣卞害闆嗘垚
- **[SOCIAL-1] 娴忚鍣ㄥ嵆 API**: 鏂板 `BBrowserSource` 閫傞厤鍣紝鏀寔璋冪敤鏈湴 Chrome 鎻掍欢/CLI 鑾峰彇闆悆鑷€夎偂銆佺儹闂ㄨ瘽棰樺強 Reddit 鐗瑰畾鐗堝潡鏁版嵁銆?
- **[SOCIAL-2] 鑷畾涔夐€傞厤鍣ㄩ儴缃?*: 閮ㄧ讲浜嗙鏈?`xueqiu/hot-post` 閫傞厤鍣紝鏀寔鎶撳彇闆悆鈥滀粖鏃ョ儹璁€濇祦鐨勯潪缁撴瀯鍖栨暟鎹苟杩涜 AI 娓呮礂銆?

#### 馃Л `/lead` 甯傚満棰嗚埅鑰呭伐浣滄祦
- **[WF-LEAD] 鍏ㄧ綉鎯呯华瀹¤**: 涓€閿壂鎻?4 涓淮搴︾殑 Reddit 鎶曡祫鐗堝潡锛圡eme/涓ヨ們璁ㄨ/浠峰€兼姇璧?娣卞害鍒嗘瀽锛夊強闆悆鐑偣銆?
- **[WF-LEAD] 鍗佸ぇ鐮旂┒绾跨储**: 閫氳繃 LLM 杩囨护绀句氦鍙ｆ按璐达紝鎸夌収浜嬪疄瀵嗗害銆佸崥寮堜环鍊煎拰鍏ㄥ眬涓€鑷存€т笁涓淮搴︼紝鎻愮偧骞舵€荤粨褰撳墠鏈€鍊煎緱璺熻釜鐨勫崄鏉￠€昏緫绾跨储銆?
- **[WF-LEAD] 鑷姩鍖栨姤鍛?*: 鑷姩鐢熸垚 `Reports/YYYYMMDD/YYYYMMDD_Market_Lead_Analysis.md` 骞跺悜鐢ㄦ埛涓诲姩鎺ㄩ€佹牳蹇冨紓鍔ㄣ€?

#### 馃洜锔?宸ュ叿鎬荤嚎闆嗘垚
- **[TB-1] browser.site_fetch**: 鍦?`ToolBus` 涓敞鍐屼簡娴忚鍣ㄦ姄鍙栧伐鍏凤紝鍏佽鍚勭骇 Agent锛堝瀹¤ Agent锛夊湪娣辩爺杩囩▼涓嚜鍔ㄨ皟鐢ㄦ祻瑙堝櫒鑳藉姏鑾峰彇瀹炴椂闈炲叕寮€鏁版嵁銆?

---


> **涓婚锛氬伐浣滄祦绮剧偧 鈥?娑堥櫎鍐椾綑銆佸己鍖栨牳蹇冪爺绌堕摼璺?*
>
> V3.2 瀵?5 涓牳蹇冨伐浣滄祦杩涜浜嗙簿鐐间笌閲嶅啓锛屾秷闄や簡鍛戒护闂寸殑鍔熻兘閲嶅彔锛屽皢绾剼鏈寘瑁呭櫒鍗囩骇涓哄畬鏁寸殑鎼滅储椹卞姩宸ヤ綔娴侊紝骞跺缓绔嬩簡娓呮櫚鐨勭爺绌跺懡浠ゅ眰绾э細`/deep`锛堥娆″缓妗ｏ級鈫?`/update`锛堝畾鏈熷埛鏂帮級鈫?`/quick`锛堜簨浠跺揩璇勶級銆?

### 鏍稿績鍗囩骇锛? 椤癸級

#### 馃攧 `/update` 鍏ㄩ潰閲嶅啓 鈥?鏃堕棿椹卞姩鍏徃鎯呮姤鍒锋柊
- **[WF-1] 閲嶆柊瀹氫綅**锛氫粠绌哄３鑴氭湰鍖呰鍣ㄩ噸鍐欎负瀹屾暣宸ヤ綔娴侊紝鏄庣‘瀹氫綅涓恒€屾椂闂撮┍鍔ㄣ€嶇殑瀹氭湡鍒锋柊锛?-4 鍛ㄥ洖椤撅級锛屼笌浜嬩欢椹卞姩鐨?`/quick` 褰诲簳鍖哄垎
- **[WF-1] 鍏娴佺▼**锛歋tep 0 鐭ヨ瘑搴撻妫€锛堜笁绾у熀鍑嗘煡鎵撅級鈫?Step 1 澶氱淮鎯呮姤閲囬泦锛?-6 娆℃悳绱㈣鐩栨柊闂?鍒嗘瀽甯?鑲′环/琛屼笟锛夆啋 Step 2 杈归檯鍙樺寲鍒嗘瀽锛堜簨浠舵椂闂寸嚎 + 鍩哄噯瀵规瘮琛?+ 閫昏緫鏍￠獙锛夆啋 Step 3 浼板€间笌鎸佷粨瀹¤ 鈫?Step 4 鎶ュ憡鐢熸垚 鈫?Step 5 淇濆瓨涓庨€氱煡
- **[WF-1] 杈归檯鍙樺寲琛?*锛氭牳蹇冭緭鍑轰负銆屼笂娆″熀鍑?vs 褰撳墠鐘舵€併€嶅姣旇〃锛岃鐩栨牳蹇冮€昏緫/璐㈠姟琛ㄧ幇/浼板€兼按骞?鍒嗘瀽甯堝叡璇?琛屼笟鍦颁綅浜斾釜缁村害

#### 馃幆 `/deep` Phase D 鐩戞帶娓呭崟锛堝悎骞?`/radar`锛?
- **[WF-2] 鏂板 Phase D**锛氬皢鐙珛鐨?`/radar` 鐩戞帶娓呭崟鍔熻兘鍚堝苟涓?`/deep` 鐨勭鍥涢樁娈碉紝寤虹珛銆屾繁鐮斿嵆寤烘。 + 寤烘。鍗崇洃鎺с€嶇殑涓€浣撳寲娴佺▼
- **[WF-2] 鍥涚淮鐩戞帶**锛欴1 绔炲搧闆疯揪锛?-5 瀹剁珵鍝?+ 鍙嶅悜瑙ｈ瑙勫垯锛夈€丏2 浜т笟閾剧洃鎺э紙涓婃父鎴愭湰 + 涓嬫父闇€姹傦級銆丏3 瀹忚涓庤涓氳瀵熸寚鏍囷紙鍚Е鍙戦槇鍊硷級銆丏4 鍏抽敭鏃ュ巻锛堣储鎶?浼氳/瑙ｇ锛?
- **[WF-2] 鎶ュ憡妯℃澘鎵╁睍**锛氭柊澧?Section 4銆屾寔缁洃鎺ф竻鍗曘€嶏紝鍚洓寮犵粨鏋勫寲琛ㄦ牸

#### 馃棏锔?`/radar` 鍒犻櫎
- **[WF-3] 鍔熻兘鍚堝苟**锛歚/radar` 鍏ㄩ儴鍔熻兘宸茶縼鍏?`/deep` Phase D锛屽垹闄?`radar.md` 宸ヤ綔娴佹枃浠讹紝鍛戒护鎬绘暟 17 鈫?16

#### 馃彿锔?`/theme` 鍏ㄩ潰閲嶅啓 鈥?A鑲′富棰樻姇璧勫彂鐜颁笌閫夎偂
- **[WF-4] 浠庤剼鏈埌宸ヤ綔娴?*锛氫粠 21 琛?Tushare 鑴氭湰鍖呰鍣ㄩ噸鍐欎负瀹屾暣鐨勬悳绱㈤┍鍔ㄥ伐浣滄祦锛屾敮鎸佽嚜鍔ㄥ彂鐜板拰鎸囧畾涓婚涓ょ妯″紡
- **[WF-4] 涓婚鍙戠幇**锛?-4 娆℃悳绱紙娑ㄥ仠澶嶇洏/璧勯噾娴佸悜/杩炴澘榫欏ご锛夛紝鍥涚淮绛涢€夋爣鍑嗭紙杩炵画鎬?璧勯噾纭/閫昏緫鍙В閲?瀹归噺瓒冲锛?
- **[WF-4] 閫昏緫閾炬瀯寤?*锛氥€岃Е鍙戜簨浠?鈫?浼犲鏈哄埗 鈫?鍙楃泭鐜妭 鈫?鍏蜂綋鏍囩殑銆嶅畬鏁存帹婕旓紝鍚洓闃舵鎸佺画鎬у垽鏂紙鍚姩/鍔犻€?楂樻疆/閫€娼級
- **[WF-4] 涓夊眰鏍囩殑绛涢€?*锛氶緳澶达紙鎵撴澘/杩芥定锛夆啋 鏍稿績璺熼锛堜綆鍚?鍥炶皟锛夆啋 娼滀紡锛堟彁鍓嶅竷灞€锛夛紝姣忓彧鍚?7 椤瑰叧閿暟鎹?
- **[WF-4] 浜ゆ槗绾緥鍐呭祵**锛氬崟鍙粨浣嶄笂闄?2-3%銆佺牬浣嶅嵆璧般€佷富棰橀€€娼叏鎾わ紝涓庢姇璧勭姸鎬佸崱銆屽崼鏄熶粨蹇繘蹇嚭銆嶅榻?

#### 鈴?`/scan` 缃戠粶鏃堕棿鏍″噯
- **[WF-5] `scripts/get_time.py`**锛氭柊寤虹綉缁滄椂闂磋幏鍙栬剼鏈紝涓夌骇闄嶇骇锛坵orldtimeapi 鈫?timeapi.io 鈫?NTP锛夛紝瑙ｅ喅鏈湴鏃堕挓婕傜Щ瀵艰嚧甯傚満璺敱閿欒鐨勯棶棰?
- **[WF-5] 鑷€傚簲鎼滅储**锛歚/scan` 鎼滅储闃舵鏍规嵁缃戠粶鏃堕棿鍔ㄦ€佽矾鐢辫嚦 LIVE/HOT 甯傚満锛岄厤棰濆垎閰嶆洿绮惧噯

### 鏋舵瀯鍙樺寲
- **鐮旂┒鍛戒护灞傜骇纭珛**锛歚/deep`锛堥娆″缓妗ｏ紝8+ 娆℃悳绱級鈫?`/update`锛堝畾鏈熷埛鏂帮紝5-6 娆℃悳绱級鈫?`/quick`锛堜簨浠跺揩璇勶紝2-3 娆℃悳绱級锛屼笁绾у垎宸ユ槑纭?
- **鍛戒护鎬绘暟**锛?7 鈫?16锛堝垹闄?`/radar`锛屽姛鑳介浂鎹熷け锛?
- **鑷劧璇█鏆楀彿鎵╁睍**锛氭柊澧炪€孾鑲＄エ] 鏈€杩戞€庝箞鏍蜂簡銆嶁啋 `/update`

---

## [V3.1] 鈥?2026-03-10 鉁?宸插彂甯?

> **涓婚锛歅hase 7 涓诲姩鏅鸿兘 鈥?浠庛€屼綘闂畠绛斻€嶅埌銆岀郴缁熶富鍔ㄦ壘浣犮€?*
>
> V3.1 鏄郴缁熻繄鍚戙€屾姇璧勫壇椹鹃┒銆嶇殑鍏抽敭涓€姝ャ€傛柊澧?3 涓嚜鍔ㄦ帹閫佽剼鏈?+ 璋冨害閰嶇疆锛屽皢鏃ュ父鎶曠爺鎯呮姤鐢辫鍔ㄨЕ鍙戝崌绾т负涓诲姩鎺ㄩ€併€?

### 鏍稿績鍗囩骇锛? 椤癸級

#### 馃搮 璐㈡姤鏃ュ巻鎻愰啋 (7.2)
- **[P7-2] `scripts/earnings_reminder.py`**: 姣忓懆鏃ヨ嚜鍔ㄦ壂鎻忔寔浠撲腑涓嬩竴鍛ㄦ湁璐㈡姤鐨勬爣鐨勶紙閫氳繃 yfinance 鏌ヨ锛夛紝鎻愬墠閫氳繃 Telegram 鎺ㄩ€佹彁閱掞紝骞跺紩瀵兼墽琛?`/radar` 棰勬銆?

#### 馃寘 鏅ㄦ姤鑷姩鎺ㄩ€?(7.3)
- **[P7-3] `scripts/morning_scan_push.py`**: 姣忎釜浜ゆ槗鏃ユ棭 8:00 鑷姩璇诲彇褰撴棩 `Market_Scan.md` 鎶ュ憡锛屾彁鍙栨爣棰?鎽樿/鎸佷粨棰勮/椋庨櫓璀﹀憡鍥涗釜娈佃惤锛屾帹閫佺簿绠€鏅ㄦ姤鍒?Telegram銆?

#### 馃搳 鎸佷粨鍛ㄦ姤 (7.4)
- **[P7-4] `scripts/weekly_position_report.py`**: 姣忓懆浜旀敹鐩樺悗鑷姩璁＄畻鎸佷粨鏈懆娑ㄨ穼骞咃紝閫氳繃 Gemini API 鐢熸垚涓€娈靛仴搴峰害 AI 鍒嗘瀽鎽樿锛屾帹閫佸埌 Telegram銆?

#### 馃 Bot 鍛戒护鎵╁睍 & 璋冨害鑴氭湰
- **[P7-BOT]** `bot/telegram_bot.py` 鏂板涓変釜鎵嬪姩瑙﹀彂鍛戒护锛歚/morning`銆乣/earnings`銆乣/weekly`锛屽厑璁哥敤鎴烽殢鏃跺湪 Bot 涓竴閿Е鍙戝畾鏃朵换鍔°€?
- **[P7-BAT] `scheduler.bat`**: 涓€閿敞鍐屽叏閮ㄤ笁涓换鍔″埌 Windows Task Scheduler锛岄檮甯﹀嵏杞借鏄庛€?

### 璐ㄩ噺淇濋殰
- TDD 妯″紡寮€鍙戯細鎵€鏈変笁涓剼鏈潎鍏堝啓娴嬭瘯锛坄tests/test_phase7_scripts.py`锛夛紝鍚庡啓瀹炵幇锛?2/12 娴嬭瘯鍏ㄩ儴閫氳繃銆?
- 瀹屽叏 Mock 闅旂锛氭祴璇曚腑鍏ㄩ儴澶栭儴渚濊禆锛坹finance銆丟emini API銆乀elegram锛夊潎閫氳繃 `unittest.mock` 闅旂锛屼笉浜х敓鐪熷疄缃戠粶璇锋眰銆?



> **涓婚锛氬叏缃戞繁搴︾爺绌堕泦鎴愪笌閰嶉鍔ㄦ€佷紭鍖?*
>
> V3.0 鏄郴缁熻蛋鍚?鍏ㄧ煡鍩熺爺绌?鐨勯噸瑕侀噷绋嬬銆傛繁搴︽暣鍚堜簡绗笁鏂?AI 鏈嶅姟锛圴alueCell锛夛紝瀹屽杽浜嗗畯瑙?寰鐨勮嚜鍔ㄥ垎閰嶉€昏緫锛岀郴缁熶唬鍙锋寮忔鍏?3.x 鏃朵唬銆?

### 鏍稿績鍗囩骇锛? 椤癸級

#### 馃寪 娣卞害鐮旂┒涓彴鎺ュ叆锛圴alueCell Integration锛?
- **[VC-1] 澶栭儴 AI 鐮旂┒鍛樻暣鍚?*锛欳LI 寮曟搸 (`research_cli.py`) 鍙?`DataHub` 鏁版嵁涓績鍏ㄦ柊鎺ュ叆 ValueCell 娣卞害鐮旂┒ API銆傛柊澧?`valuecell_deep_research(ticker)` 涓?`valuecell_news(ticker)` 涓や釜 Agent Tool銆?
- **[VC-2] 浼橀泤闄嶇骇鏈哄埗锛圙raceful Degradation锛?*锛氱郴缁熺骇搴斿澶栭儴渚濊禆涓柇銆傚鏋?`.env` 鏈厤缃?`VALUECELL_BASE_URL` 鎴栬鏈嶅姟绂荤嚎锛孉gent 宸ュ叿浼氳嚜鍔ㄨ繑鍥炲甫鏈夊叿浣撳紓甯镐俊鎭殑瀛楃涓诧紝骞堕€€鍥炰娇鐢?`search_web`锛岀‘淇濇暣涓爺绌跺伐浣滄祦锛堝挨鍏舵槸 `/deep`锛夋案涓嶅穿婧冦€?
- **[VC-3] 动态数据聚合中心**：重构了 `services/datahub`，引入基于适配器模式的 `ValueCellNewsSource`，使系统在执行 `/deep` 或 legacy 定时新闻抓取任务时，都可以并行读取高质量外源情报。

#### 鈿栵笍 宸ヤ綔娴佽祫婧愰噸鍒嗛厤锛圵orkflow Rebalance锛?
- **[FLOW-1] `/scan` 鍏ㄦ櫙鎵弿閰嶉浼樺寲**锛氶拡瀵瑰洓甯傚満锛堢編銆佹腐銆佹棩銆丄锛夌殑鎼滅储娑堣€楅檺棰濓紙32娆★級杩涜浜嗕富娆￠噸鏂板€炬枩銆傛棩鑲＄洏涓紙LIVE锛変笌鍒氭敹鐩橈紙HOT锛夐厤棰濆噺鍗婏紙鍒嗗埆闄嶄负3娆′笌2娆★級锛屽鍑洪厤棰濆叏閮ㄨ娓＄粰A鑲″競鍦恒€?

#### 馃悰 绯荤粺寮哄寲涓庝慨澶嶏紙System Hardening锛?
- **[SYS-1] 鐗堟湰鏋舵瀯鍗囩骇**锛氱郴缁熶富鏂囨。 `SYSTEM.md` 鍜?CLI 鍏ュ彛鍏ㄩ潰鍗囩骇鑷?v3.0銆傜郴缁熸暣浣撹繍琛屾洿绋冲畾銆?

---

## [V2.5] 鈥?2026-03-04 

> **涓婚锛氱煡璇嗛杞?脳 鍏ㄩ摼璺棴鐜?脳 Bot 鍐崇瓥瀹屾暣鍖?*
>
> V2.5 鏄?V2.1 鐨勯噸澶у崌绾э紝绯荤粺鎬цВ鍐充簡銆屾暟鎹宀涖€佺煡璇嗙Н绱柇鐐广€佸弽棣堝洖璺┖缃€丅ot 鍛戒护缂哄け銆佽矾寰勭‖缂栫爜銆嶄簲澶у巻鍙查仐鐣欓棶棰橈紝瀹炵幇浜嗕粠淇℃伅閲囬泦鍒板喅绛栧綊妗ｇ殑瀹屾暣鏁版嵁闂幆銆?

### 鏍稿績鍗囩骇锛?1 椤癸級

#### 馃 鐭ヨ瘑椋炶疆锛圞nowledge Flywheel锛?

- **[KB-1] 鐭ヨ瘑搴撻妫€鏈哄埗**锛氬湪 `deep`銆乣quick`銆乣buy`銆乣sell`銆乣value`銆乣radar`銆乣update` 7 涓伐浣滄祦澶撮儴鍔犲叆 **Step 0 涓ょ骇鐭ヨ瘑搴撻妫€**锛堚憼 鏌?`KB_INDEX.md` 绱㈠紩绉掔骇鍛戒腑 鈫?鈶?鏈懡涓墠鎵洰褰曪級锛屽交搴曟秷闄ゃ€岄噸澶嶄粠闆跺紑濮嬨€嶉棶棰樸€傛姤鍛婇《閮ㄨ嚜鍔ㄦ爣娉ㄣ€岎煋?鍩轰簬鍘嗗彶妗ｆ銆嶆垨銆岎焼?棣栨鍒嗘瀽銆嶃€?

- **[KB-2] 缁撴瀯鍖栫煡璇嗗崱锛圷AML Front Matter锛?*锛氱煡璇嗗崱鐗囧崌绾т负 YAML 鏍囧噯鏍煎紡锛堝惈 `ticker`/`type`/`status`/`tags`/`linked_report` 浜斿瓧娈碉級+ 5鑺傚浐瀹氭鏂囷紙鏍稿績閫昏緫/鏁版嵁閿氱偣/杈归檯鍙樺寲/椋庨櫓/鍘嗗彶璁板綍锛夈€傜幇鏈?13 寮犲崱鐗囧叏閮ㄦ壒閲忚縼绉汇€俙add.md` 宸ヤ綔娴佸悓姝ュ崌绾т负缁撴瀯鍖栨ā鏉裤€?

- **[KB-3] KB_INDEX.md 涓夌骇绱㈠紩**锛氭柊寤?`Memory_Layer/Knowledge_Base/KB_INDEX.md`锛屾寜涓夌被缁撴瀯鍖栫鐞嗘墍鏈夊崱鐗囷紙涓偂妗ｆ / 琛屼笟涓婚 / 瀹忚浜嬩欢锛夛紝姣忚鍚?6 鍒椾緵 Step 0 鐩存帴瀹氫綅銆俙/add` 鑷姩杩藉姞鏂拌骞舵洿鏂般€屾渶鍚庢洿鏂般€嶆棩鏈燂紝瀹屾垚鍚庡悜鐢ㄦ埛灞曠ず鏂板琛屼緵鏍歌鍏抽敭璇嶃€?

- **[KB-4] 宸ヤ綔娴?`/add` 鎻愮ず**锛歚deep`銆乣buy`銆乣sell`銆乣value`銆乣radar`銆乣update` 鍏釜宸ヤ綔娴佺殑淇濆瓨鑺傛湯灏惧姞鍏ュ樊寮傚寲 `/add` 寤鸿锛屽舰鎴愩€屽垎鏋?鈫?褰掓。銆嶇殑涓诲姩鐭ヨ瘑绉疮寰幆銆?

#### 馃搳 鏁版嵁灞傜粺涓€锛圖ata Unification锛?

- **[DATA-1] 鎸佷粨鏁版嵁鍗曚竴鐪熺浉鏉ユ簮**锛氫互 `Config/holdings.json` 涓哄敮涓€鐪熺浉锛屽交搴曟秷闄?V2.1 涓簲濂楀啿绐佹暟鎹紙纭紪鐮?/ MD / CSV / JSON / 宸ヤ綔娴佸唴鑱旓級銆俙parse_positions.py` 閲嶅啓涓哄弻杈撳嚭锛圝SON + MD锛夛紝鏀寔 `--extra-cash` 鍙傛暟锛沗data_manager.py` 鍒犻櫎鏃?`ASSET_CONFIG` 纭紪鐮侊紝鏀圭敤鍔ㄦ€?`load_holdings()`锛沗scan`銆乣position`銆乣buy`銆乣sell` 宸ヤ綔娴佺粺涓€鏀逛负 JSON 浼樺厛銆丮D 鍥為€€銆?

- **[DATA-2] 涓€у寲鍋忓ソ鎺ュ叆**锛歚scan.md` 鎸佷粨棰勮灞傛柊澧炰笁姝ヨ鍙栵紙`holdings.json` 鈫?`鎴戠殑鎶曡祫鐘舵€佸崱.md` 鈫?`鎴戠殑鍏宠仈鍋忓ソ.md`锛夛紝灏嗙敤鎴风殑椋庨櫓鍋忓ソ銆佹搷浣滅蹇屻€佹寔浠撳叧鑱斿叧閿瘝娉ㄥ叆鎼滅储璇嶏紝瀹炵幇鐪熸涓€у寲棰勮锛涙枃浠朵负鍒濆妯℃澘鏃惰嚜鍔ㄨ烦杩囥€?

#### 馃 鑴氭湰灞傝川閲忓崌绾э紙Script Quality锛?

- **[SCRIPT-1] 妯″瀷鍗囩骇 + KB/鎸佷粨娉ㄥ叆**锛氭柊寤?`scripts/kb_holdings.py` 鍏辩敤妯″潡锛坄load_kb_context()` + `load_holdings_context()`锛夈€俙quick_event.py` / `update_company.py` 妯″瀷 `gemini-2.0-flash` 鈫?`gemini-3.0-flash`锛屾敞鍏?KB 鍘嗗彶妗ｆ鍜屾寔浠撶姸鎬侊紱`generate_market_scan.py` 鍗囩骇 鈫?`gemini-3.0-flash`锛屾柊澧炪€屾寔浠撻璀︺€嶈妭锛堭煙?馃敶 鏍囨敞锛夈€?

- **[SCRIPT-2] LLM 瀹㈡埛绔ā鍨嬫洿鏂?*锛歚core/llm_client.py` CLI 榛樿妯″瀷鍗囩骇涓?`gemini-3.1-flash-lite-preview`锛孭ro 妯″瀷鍗囩骇涓?`gemini-3.1-pro-preview`锛堝潎宸?API 杩為€氶獙璇侊級銆?

#### 馃攧 鍙嶉鍥炶矾婵€娲伙紙Feedback Loop锛?

- **[FEEDBACK] `/rethink` 鍏ㄩ摼闂幆**锛歚rethink.md` 鏂板 Step 5銆岃寰嬫彁鐐笺€嶏紝寮哄埗鎵ц鍏被婕忔礊鍒嗙被锛屽皢缁撴灉鍐欏叆鏂板缓鐨?`Feedback_Loop/Pattern_Log.md`锛涘悓涓€婕忔礊绱 鈮? 娆¤嚜鍔ㄥ缓璁洿鏂?`Memory_Layer/Investment_Persona.md`銆俙Investment_Persona.md` 鏂板绗?7 鑺傘€屾紨杩涜褰曘€嶏紝鎶曡祫鐢诲儚闅忓鐩樿嚜鍔ㄨ繘鍖栵紝褰诲簳缁堟 Feedback_Loop 鐩綍绌虹疆鐘舵€併€?

#### 馃 Bot 灞傚喅绛栧畬鏁村寲锛圔ot Commands锛?

- **[BOT-1] 鍥涗釜鍐崇瓥鍛戒护琛ュ叏**锛歚research_cli.py` 鍜?`bot/telegram_bot.py` 鍚屾琛ュ厖 `/buy`銆乣/sell`銆乣/position`銆乣/rethink` 鍥涗釜鍐崇瓥鍛戒护锛堜箣鍓嶄粎 IDE 鍙敤锛孊ot 鏃犳硶瑙﹀彂锛夈€俙/start` 甯姪鑿滃崟閲嶆帓涓哄洓绫诲竷灞€锛氿煋婂競鍦哄垎鏋?/ 馃攳涓偂鐮旂┒ / 馃挵鍐崇瓥鍛戒护 / 馃摎鐭ヨ瘑搴撱€?

- **[BOT-2] knowledge_base.py 鏍煎紡缁熶竴**锛歚core/knowledge_base.py` 鐨?`save_knowledge_card()` 鏀逛负杈撳嚭 YAML Front Matter 鏂版牸寮忥紝鏂板 `_update_kb_index()` 鍐欏叆 `KB_INDEX.md`锛汢ot 璺緞鎵ц `/add` 鐜颁笌 IDE Agent 璺緞浜у嚭鏍煎紡瀹屽叏涓€鑷淬€?

#### 馃敡 Bug 淇锛圔ug Fixes锛?

- **[FIX-1] legacy V1 自动监控入口路径硬编码**：将早期指向 `d:/AI/Auto/system/` 的路径改为 `PROJECT_ROOT` 相对路径，并在配置缺失时给出模板指引。

- **[FIX-2] ai寤鸿鐩綍鑷姩缁存姢**锛歚radar.md` 淇濆瓨鑺傛柊澧炲悓姝ュ揩鐓у埌 `Config/ai寤鸿/鎶曡祫闆疯揪_[鏃ユ湡].md`锛岃鐩綍浠庢鑷姩缁存姢锛屽缁堝瓨鏀炬渶鏂颁竴鏈熼浄杈惧缓璁€?

- **[FIX-3] verify.md 淇濆瓨姝ラ寮哄埗鍖?*锛氳緭鍑鸿妭鏄庣‘鏍囨敞銆屸殸锔?蹇呴』鍏?write_to_file 鍐?notify_user锛屼弗绂佸彧鍥炲涓嶄繚瀛樸€嶏紝闃叉婕忓瓨鎶ュ憡銆?

---

## [V2.1] 鈥?2026-02-16

> **涓婚锛氭暟鎹畨鍏ㄥ己鍖?+ 鏂囨。鏍囧噯鍖?*
>
> 瀹氫綅锛氬湪 V2 鍩虹涓婂仛鐢熶骇绾у姞鍥猴紝涓昏闈㈠悜浠ｇ爜寮€婧愬噯澶囧拰澶氳澶囧崗鍚屻€?

### 鏂板鍔熻兘
- **鐜鍙橀噺闅旂 (`.env`)**: 鎵€鏈?API Key锛圙emini銆乀elegram銆乀avily銆丅rave銆乀ushare锛変粠浠ｇ爜鍐呯‖缂栫爜杩佺Щ鑷?`.env` 鏂囦欢锛宍.gitignore` 鍚屾鏇存柊浠ラ槻姝㈠瘑閽ユ硠闇?
- **鏂板鍛戒护 `/radar`**: 涓哄叧娉ㄤ釜鑲＄敓鎴愮珵鍝?浜т笟閾?瀹忚鐨勬棩甯哥洃鎺?Checklist锛坄YYYYMMDD_Ticker_Radar.md`锛?
- **鏂板鍛戒护 `/buy`**: 鍏ㄩ潰涔板叆鍓嶅鏌ワ紝鍚澘鍧?Beta 鐔旀柇銆佺泩浜忔瘮璁＄畻銆丗OMO 鑷锛岃緭鍑轰笁鑹插垽鍐筹紙馃煝馃煛馃敶锛?
- **鏂板鍛戒护 `/sell`**: 鍗栧嚭鍐崇瓥瀹℃煡锛屽惈鍏ュ満瀹氭€у洖婧€侀鏍兼紓绉绘娴嬨€?绫诲崠鍑轰俊鍙锋壂鎻?
- **鏂板鍛戒护 `/option`**: 涓夊ぇ鏈熸潈鍦烘櫙锛圕overed Call / Cash Secured Put / Protective Put锛夌瓥鐣ヨ绠?
- **鏂板鍛戒护 `/position`**: 鎸佷粨浣撴锛屽惈闀跨嚎/鐭嚎/鐜伴噾姣斾緥瀹¤銆佽禌閬撻泦涓害銆佺浉鍏虫€ф壂鎻忋€佸啀骞宠　寤鸿
- **鏂板鍛戒护 `/macro`**: 瀹忚浜嬩欢鍘嬪姏娴嬭瘯锛屼笁缁村害锛堣创鐜扮巼/涓氬姟浼犲/閬块櫓灞炴€э級璇勪及鎸佷粨鍐插嚮
- **鏂板鍛戒护 `/rethink`**: 浜ゆ槗澶嶇洏锛屽惈鐭ヨ鍚堜竴妫€鏌ャ€佽繍姘?vs 瀹炲姏鍖哄垎銆?-10 绾緥璇勫垎
- **鎶ュ憡褰掓。瑙勫垯鏄庣‘鍖?*: 娣卞害鐮旂┒ (`/deep`銆乣/value`) 鈫?`Reports/deepdive/`锛涙棩甯稿垎鏋?鈫?`Reports/YYYYMMDD/`
- **`config.yaml.example` / `watchlist.json.example`**: 鎻愪緵瀹夊叏鐨勯厤缃ā鏉匡紝渚夸簬鏂扮幆澧冨揩閫熼儴缃?
- **`DEPLOY.md`**: Windows/Linux VPS 鐨勫畬鏁撮儴缃叉枃妗?
- **`System_Manual.md` / `System_Manual.html`**: 缁煎悎绯荤粺浣跨敤鎵嬪唽锛堝弻鏍煎紡锛?

### Bug 淇
- 淇澶氬宸ヤ綔娴佹枃浠朵腑鎼滅储閰嶉鍒嗛厤涓嶆槑纭鑷?Agent 杩囧害鎼滅储鐨勯棶棰?
- 修复 V2 时期 legacy V1 自动监控入口的配置路径问题（部分修复）

### 鏋舵瀯鍙樺寲
- 鍛戒护浣撶郴浠?7 涓紙V1/V2锛夋墿灞曡嚦 **14 涓?*锛堝鍔?`/buy`銆乣/sell`銆乣/option`銆乣/position`銆乣/macro`銆乣/rethink`銆乣/radar`锛?
- 璇█瑙勮寖缁熶竴锛氭墍鏈夎緭鍑哄己鍒朵娇鐢ㄧ畝浣撲腑鏂囷紝涓撴湁鍚嶈瘝鍙繚鐣欒嫳鏂?

---

## [V2.0] 鈥?2026-01 鍒?

> **涓婚锛氬弻寮曟搸铻嶅悎 鈥?V1 Agent 寮曟搸 脳 Core System 涓夊眰淇℃伅涓彴**

### 鏂板鍔熻兘
- **涓夊眰鏋舵瀯 (Eyes 鈫?Brain 鈫?Memory)**: 姝ｅ紡纭珛淇℃伅閲囬泦/LLM澶勭悊/鐭ヨ瘑褰掓。涓夊眰鍒嗙鏋舵瀯
- **P1-P15 鎶€鑳界煩闃?*: 浠?P1(Genesis 涓偂鍩虹煶寤烘。) 鍒?P15(鏂伴珮棰勮) 鐨勫畬鏁村垎鏋愭妧鑳芥睜
- **鑷劧璇█鏆楀彿绯荤粺**: 鏀寔涓枃鑷劧璇█瑙﹀彂鍛戒护锛?璋冪爺 MCO" 鈫?P1銆?鎴戞兂涔?NVDA" 鈫?P5 FOMO 鏉€鎵嬨€?浼板€艰吹涓嶈吹" 鈫?P9 鍙嶅悜DCF 绛夛級
- **`Memory_Layer/` 鐭ヨ瘑灞?*: 缁熶竴褰掓。鐩綍锛屽惈 `Knowledge_Base/`锛堢爺绌跺崱鐗囷級銆乣Investment_Persona.md`锛堟姇璧勭敾鍍忥級銆乣Trade_Log/`锛堜氦鏄撴棩蹇楋級
- **`Feedback_Loop/`**: 寮曞叆鍙嶆€濊凯浠ｆ満鍒讹紝璁板綍姣忔浠诲姟鍚庣殑鏀硅繘绗旇
- **LLM 鍙屾ā寮?*: 閫氳繃 `.env` 涓?`LLM_MODE` 鎺у埗 `desktop`锛圛DE Agent 鐩存帴澶勭悊锛? `vps`锛坓oogle-genai SDK API 璋冪敤锛? `auto`
- **澶氭暟鎹簮鏁村悎**: RSS 璁㈤槄 + yfinance锛堢編/娓?鏃?A 鑲★級+ tushare锛圓 鑲¤缁嗘暟鎹級+ Tavily锛堜富鍔涙悳绱級+ Brave锛堝鐢ㄦ悳绱級骞惰仈
- **`Obsidian_Vault/` 鍚屾锛堝彲閫夛級**: 鏀寔灏嗘姤鍛婂悓姝ヨ嚦 Obsidian 鐭ヨ瘑搴?

### Bug 淇
- 淇 V1 涓?`data_manager.py` 鏃犳硶姝ｇ‘鎷夊彇 A 鑲℃暟鎹殑闂锛堟敼鐢?tushare 涓撶敤鎺ュ彛锛?
- 淇 Bot 鍦?VPS 涓婂穿婧冨悗鏃犳硶鑷姩閲嶅惎鐨勯棶棰橈紙寮曞叆 `bot_service.py` + `Systemd` 鏈嶅姟瀹堟姢锛?

### 鏋舵瀯鍙樺寲
- V1 鐨?Telegram Bot 鎴愪负涓変釜鍏ュ彛涔嬩竴锛屼笉鍐嶆槸鍞竴鍏ュ彛锛堟柊澧?IDE Agent 妗岄潰妯″紡銆丆LI 妯″紡锛?
- Core System 涓?V1 骞跺瓨锛屼絾鏈畬鍏ㄦ墦閫氾紙瀛樺湪"鍙岃建鎾曡"锛氭闈?IDE 楂樿川閲?vs VPS 鑴氭湰鑷姩鍖栵級

---

## [V1.0] 鈥?2025 骞村簳

> **涓婚锛歁VP 鈥?7鍛戒护 Agent 寮曟搸 + Telegram Bot**

### 鏍稿績鍔熻兘
- **7 涓枩鏉犲懡浠ゅ垵濮嬬増**锛歚/scan`銆乣/deep`銆乣/quick`銆乣/value`銆乣/verify`銆乣/update`銆乣/add`
- **Telegram Bot**锛歚telegram_bot.py`锛屾敮鎸佸璇濆紡瑙﹀彂鍛戒护锛孊ot Service 鍚庡彴瀹堟姢
- **Market Sentinel**锛歚sentinel/market_sentinel.py`锛屽畾鏃舵壂鎻忓競鍦哄紓鍔ㄥ苟鎺ㄩ€侀璀?
- **鎶ュ憡钀界洏鏈哄埗**锛氭墍鏈夊懡浠ゅ繀椤荤敓鎴?Markdown 鏂囦欢锛岀姝粎鎵撳嵃鍒版帶鍒跺彴
- **Knowledge Base 鍒濈増**锛歚/add` 鍛戒护灏嗙爺绌舵礊瀵熸彁鐐间负鐭ヨ瘑鍗＄墖瀛樺叆 `Memory_Layer/Knowledge_Base/`
- **`UPDATE_LOG.md`**锛欰I 浠诲姟瀹屾垚鍚庣殑鍔ㄦ€佸弽鎬濊褰曪紙鍚悳绱㈢己澶?鏀硅繘鏂规/鐢ㄦ埛鍙嶉锛?

### 鎶€鏈爤
- LLM锛欸oogle Gemini API锛坄gemini-2.0-flash` 鐢ㄤ簬鑴氭湰锛岄珮璐ㄩ噺浠诲姟鐢?`gemini-2.5-pro`锛?
- 鏁版嵁锛歽finance + RSS + Brave Search + Tavily
- 閫氱煡锛歱ython-telegram-bot
- 鎶ュ憡鏍煎紡锛歁arkdown锛堟寜鏃ユ湡鍜岀爺绌剁被鍨嬪垎绫诲綊妗ｏ級

### 宸茬煡闂锛堝湪 V2 涓慨澶嶏級
- API Key 纭紪鐮佸湪 `config.yaml` 涓紝瀛樺湪瀹夊叏椋庨櫓
- 鎵€鏈夊懡浠ゅ潎閫氳繃 CLI 鎴?Bot 瑙﹀彂锛屾棤 IDE 鐩存帴浜や簰妯″紡
- 鏁版嵁鑾峰彇閫昏緫锛坄data_manager.py`锛変笌鎶ュ憡鐢熸垚閫昏緫鑰﹀悎锛岄毦浠ュ崟鐙淮鎶?

---

## 鐗堟湰婕旇繘涓€瑙?

```
V1.0  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2025骞村簳
  7鍛戒护 + Telegram Bot + Market Sentinel
  MVP锛孏emini API 椹卞姩锛孊ot 瑙﹀彂涓轰富瑕佸叆鍙?

V2.0  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2026骞?鏈?
  V1 Agent 寮曟搸 + Core System 涓夊眰鏋舵瀯铻嶅悎
  鏂板鑷劧璇█鏆楀彿 + P1-P15 鎶€鑳界煩闃?+ Memory灞?
  LLM 鍙屾ā寮忥紙IDE 妗岄潰 / VPS 鑴氭湰锛夊苟瀛?

V2.1  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2026骞?鏈?
  鏁版嵁瀹夊叏锛?env 闅旂 API Key锛? 鏂囨。鏍囧噯鍖?
  鍛戒护浣撶郴鎵╁睍鑷?14 涓紙澧炲姞浜ゆ槗鍐崇瓥 + 缁勫悎绠＄悊 + 澶嶇洏绫伙級
  鐢熶骇绾у姞鍥猴紝鏀寔澶氳澶?澶氬钩鍙伴儴缃?

V2.5  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2026骞?鏈?鏃?
  鐭ヨ瘑椋炶疆锛圞B 涓ょ骇棰勬 + YAML 缁撴瀯鍖栧崱鐗?+ KB_INDEX锛?
  鏁版嵁灞傜粺涓€锛坔oldings.json 鍗曚竴鐪熺浉 + 涓€у寲鍋忓ソ娉ㄥ叆锛?
  鑴氭湰璐ㄩ噺璺冨崌锛坓emini-3.1 绯诲垪 + KB/鎸佷粨涓婁笅鏂囨敞鍏ワ級
  鍙嶉鍥炶矾婵€娲伙紙Pattern_Log + Investment_Persona 鑷姩婕旇繘锛?
  Bot 鍐崇瓥瀹屾暣鍖栵紙+4 鍐崇瓥鍛戒护锛孊ot/IDE 璺緞瀹屽叏瀵归綈锛?
  鍘嗗彶閬楃暀 Bug 娓呴浂锛堣矾寰勭‖缂栫爜 / 鏍煎紡涓嶅吋瀹?/ 淇濆瓨婕忔锛?

V3.0  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2026骞?鏈?鏃?鉁?
  鍏ㄧ綉娣卞害鐮旂┒闆嗘垚锛圴alueCell API 鏁村悎鍏ユ繁鐮旈棴鐜級
  浼橀泤闄嶇骇鏈哄埗锛堜緷璧栧垽瀹氾紝瀹曟満鏃犵紳鍒囨崲 search_web锛?
  DataHub 鏂伴椈涓彴锛圴alueCellNewsSource 閫傞厤鍣級
  宸ヤ綔娴佽祫婧愰噸鍒嗛厤锛?scan 甯傚満鎼滅储閰嶉寰€涓诲姏甯傚満鍊炬枩锛?

V3.2  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2026骞?鏈?3鏃?
  宸ヤ綔娴佺簿鐐硷紙娑堥櫎鍐椾綑銆佸己鍖栨牳蹇冪爺绌堕摼璺級
  /update 鍏ㄩ潰閲嶅啓锛堟椂闂撮┍鍔ㄥ叕鍙告儏鎶ュ埛鏂帮紝杈归檯鍙樺寲瀵规瘮琛級
  /deep +Phase D 鐩戞帶娓呭崟锛堝悎骞?/radar锛屾繁鐮斿嵆寤烘。鍗崇洃鎺э級
  /theme 鍏ㄩ潰閲嶅啓锛圓鑲′富棰樻姇璧勫彂鐜帮紝閫昏緫閾?涓夊眰鏍囩殑绛涢€夛級
  /scan 缃戠粶鏃堕棿鏍″噯锛坓et_time.py 涓夌骇闄嶇骇锛?
  鐮旂┒鍛戒护涓夌骇灞傜骇纭珛锛坉eep 鈫?update 鈫?quick锛?

V3.5  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ 2026-03-17
  绀句氦鏅鸿兘锛坆b-browser 闆嗘垚锛屾墦鐮?API 瀛ゅ矝锛?
  /lead 宸ヤ綔娴侊紙鍏ㄧ悆鎯呯华鍏辨尟瀹¤锛屽崄澶ф牳蹇冪爺绌剁嚎绱級
  鑷畾涔夐€傞厤鍣ㄩ儴缃诧紙娣卞害瀹氬埗绀句氦濯掍綋鎶撳彇閫昏緫锛?
  宸ュ叿鎬荤嚎闆嗘垚锛圓I Agent 鑷富璋冨姩娴忚鍣ㄨ兘鍔涳級
```

---

*鏈€鍚庢洿鏂帮細2026-03-17 | 缁存姢鑰咃細Antigravity + 鐢ㄦ埛鍗忎綔*
