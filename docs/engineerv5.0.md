# Anthropic 金融分析 Skills 对照评审：AlphaSystem 可借鉴清单

> **日期：** 2026-08-23
> **对照对象：** [anthropics/financial-services](https://github.com/anthropics/financial-services)（equity-research / financial-analysis 两个 vertical plugin + managed-agent cookbooks）、[anthropics/skills](https://github.com/anthropics/skills)（skill-creator 规范）
> **本方基线：** `.agent/workflows/` 17 个生效工作流 + `common/` 三份契约 + `core/report_quality.py` 门禁 + `core/toolbus/`（未接线）
> **优化目标：** 在「时间、LLM 调用成本、报告质量」三角中取最优，而非无脑加重流程。
>
> **落地状态（2026-08-23）：** 第一档 2.1–2.6 已全部实施并合入；第二档 2.8 已实施
> （buy/sell 升 Pro）；2.7、2.9 待评估。逐项状态见文末「落地记录」。

---

## 1. 核心结构差异（一句话版）

AlphaSystem 的每个 workflow 是 **1 次 LLM 入口调用 + 工具循环（≤15 轮）一次性产出全文**；Anthropic 的重型 skill（initiating-coverage、dcf-model）是 **显式多阶段状态机**：每阶段只加载对应 reference、有前置输入校验、有唯一交付物，阶段间靠**确定性脚本 + 填数字式质检**把关。

它们的质量不是靠"更长的提示词"，而是靠三件事：

1. **阶段拆分**——每次调用只做一件事，上下文只装当前阶段需要的知识；
2. **确定性校验**——可判真假的检查（数值区间、勾稽、错误值）交给 Python 脚本，返回 JSON + exit code，不让 LLM 自评；
3. **反 rubber-stamp 质检**——自检写成"填实际计数并与阈值比较"（`Page count: ___ (MUST BE 30-50)`），配 `DO NOT DELIVER IF` 硬否决清单。

这三件事里，**第 2、3 件的边际成本几乎为零**（不增加 LLM 调用），是个人系统最该先抄的。

---

## 2. 借鉴清单

### 第一档：零额外 LLM 调用，纯质量/成本收益（建议全做）

#### 2.1 把质量门禁从"子串匹配"升级为"承诺过的硬校验"

现状：`report_quality.py` 的 7 项章节检查是纯 label 子串匹配（正文出现"结论先行"四个字即通过）；`common/20-quality-gate.md` 承诺的 `evidence_table`（表格有数据行）、`ticker_match`、`live_tooling`（整轮零取证拒落盘）、`price_provenance`（价格证据行逐字核对）、`report_date` 五项**代码里并不存在**——文档在描述一个不存在的门禁。

借鉴 Anthropic 的做法（`initiating-coverage/assets/quality-checklist.md`）：

- 校验"章节下有无实质内容"（标题后至下一标题间的非空行数、证据台账表格的数据行数 ≥ N 且含 ≥1 行 Bear）；
- 把 `20-quality-gate.md` 的"8 问"从"确认良好"改成**填数字**：`证据台账行数: ___（≥5）`、`Tier1/2 来源数: ___（≥2）`、`联网取证次数: ___（≥1）`，report_quality 用正则抽取这些数字复核；
- 增加 `DO NOT DELIVER IF` 硬否决段：无价格证据行却给出目标价 → 拒；单源却给出止损/盈亏比 → 拒（这条契约已写在 `00-report-contract.md`，只差代码执行）。

顺手清理：`_tungsten_direction` 硬编码抽象成规则表；乱码 label（`缁撹鍏堣`）从根上修编码而非加变体。

#### 2.2 估值算术脚本化：LLM 只判断，不心算

现状：反向 DCF 的隐含增长率、安全边际价、盈亏比、情景概率加权全靠模型口算，折现率写死 10%。Anthropic 的分工原则很清晰（`dcf-model/scripts/validate_dcf.py`）：**可判真假/可计算的交给脚本**（terminal growth < WACC、WACC ∈ [5%,20%]、TV/EV ∈ [40%,80%]、公式重算通过），**需语境判断的留给 LLM**（假设是否合理、增长率是否超行业天花板）。

落地：写一个 `scripts/valuation_math.py`（输入 price/FCF/折现率/终值增长率，输出隐含 CAGR、半增长率对应价、敏感性小矩阵，JSON 返回），让 `/deep` `/value` `/buy` 通过已有的 `execute_python_script` 调用，报告里的数字必须来自脚本输出。这是**零额外 LLM 调用换取数字可复算**，也顺带消灭"每次跑同一标的数字都不一样"的问题。

⚠️ 反面教训也来自 Anthropic 自己：`validate_dcf.py` 写好了但 SKILL.md 全文没有一处调用它——**脚本必须在 workflow 正文里写明"何时必须跑、不过不许交付"**，否则就是死代码。我们的 `core/toolbus/`（预算+权限+审计+EvidenceRecorder）正是同一种孤儿化：写好了但 `research_cli.py` 直接绕过它用 `ToolFactory.get_tools()`。

#### 2.3 接线 toolbus 预算器 = 直接省钱

搜索预算目前有**三处真理源且互相矛盾**：17 个 workflow 各写各的（28/8/6/1/0 次）、`SYSTEM.md` 第 4 条"最多 8 次"、`settings.search.max_searches=8` 无人消费。实际运行时任何 workflow 都能无限次 `search_web`。

借鉴 Anthropic 的"预算写进契约、超限即硬停"思路：让 `research_cli.py` 走 ToolBus（代码已存在），按 workflow 配置预算上限（scan=28、theme=8、quick=1…），预算从 settings 单一来源注入提示词。**这是唯一一条直接降低调用成本的改动**，且工程量小（接线，不是新写）。

#### 2.4 数据纪律三件套补齐

`10-evidence-contract.md` 的 Tier1-4 分级和来源族判独立已经比 Anthropic 做得细（值得保留），缺的是三个便宜的补丁：

- **时效协议**（抄 `earnings-analysis` 的四步）：先写下今天日期 → 搜最新 → 确认财报在 3 个月内 → 核对 transcript 日期。直指"用训练数据里的旧财报"这一最常见失败模式；
- **缺失不留空**：表格缺数用 `-`/`N/A`，估算标 `[E]`，无法溯源的数字标 `[UNSOURCED]`——比"禁止无源数字"更可执行，因为给了模型一条合法出路，不逼它编造；
- **溯源即时化**：证据台账逐行填写发生在取证当下，禁止"最后统一补"（Anthropic 对 cell comment 的要求：`Do not defer to end`）。

#### 2.5 一张分档对照表 + 负面清单

Anthropic 用一张表把 earnings update 和 initiation 在字数/表数/图数/周转/范围上逐行对比，让模型知道"这一档**不该**做什么"。AlphaSystem 的 17 个 workflow 事实上有 快扫/快评/深研/决策/组合 五类，但篇幅约束只有全局 300 字符下限——`/quick` 和 `/deep` 用同一条底线。

落地：在 `common/00-report-contract.md` 加一张档位表（各档的字数区间、搜索预算、证据台账最少行数、是否允许给目标价），report_quality 按档位取阈值。同时抄 `Deliverables Policy: NO SHORTCUTS`：**禁止自作主张产出 completion summary / 额外文件**——理由 Anthropic 写得很直白："waste context"，对按 token 计费的个人系统就是直接省钱。

#### 2.6 修复两套提示词资产的分叉

`Skills/`（16 个 P 系列文件）与 `.agent/workflows/`（17 个生效流）框架已分叉，且 `Skills/SKILL.md` 的四个链接全是坏的（指向已改名的文件）。建议：要么把 `Skills/` 明确降级为"思维框架素材库"并修链接，要么合并进 workflows 删除冗余。双源并存 = 每次改方法论要改两处，迟早再次分叉。

### 第二档：每个深研任务多 1-2 次 LLM 调用，换报告质量（只对 Pro 档做）

#### 2.7 `/deep` `/value` 拆两阶段 + 独立 critique

Anthropic 把首次覆盖拆成 5 次强制独立调用（研究→建模→估值→图表→组装），每阶段只加载自己的 reference。对个人系统 5 段太重，但 **2 段是值得的**：

- **阶段 1（Pro）**：研究 + 证据采集，产出证据台账与分维度事实；
- **阶段 2（Flash 即可）**：拿阶段 1 产物 + 估值脚本输出做组装与质检填数。

好处不只是质量：`/deep` 现在是 20KB workflow + 15KB 契约一次性塞入再跑 15 轮工具循环，**长上下文本身就在烧 token**；拆段后每段上下文更短，Pro 调用的 token 数反而可能下降。再加一个可选的 **critique pass**（用 Flash 对照质检清单挑错，便宜），只挂在 `/deep` `/value` `/buy` 上。

#### 2.8 `/buy` `/sell` 升 Pro，而不是加轮次

模型路由目前写死 `PRO_WORKFLOWS = {"deep", "value"}`，而真正触碰真金白银的 `/buy`（可触发 `execute_trade`）和 `/sell` 走 Flash。三角权衡上，**高后果任务升模型档**比"Flash 多跑几轮"性价比高：一次 Pro 调用的成本增量远低于一次错误交易。建议 `PRO_WORKFLOWS` 改为可配置并纳入 `{buy, sell}`。

#### 2.9 Progressive disclosure 用到 `.agent/workflows/` 自己身上

讽刺的是 `Skills/references/progressive-disclosure-patterns.md` 把方法论写得很清楚，但生效的 workflows 反其道而行：`scan.md` 24KB、`deep.md` 20KB、加 15KB 契约全量注入。按 Anthropic 的三级加载：workflow 主文件只留"阶段表 + 输入校验 + 输出契约 + 负面清单"（<500 行），把"体温计分表""40+ 标题骨架"这类只在特定阶段用的内容下沉为按需 `read_file` 的 reference——模型有文件工具，提示词里写清"何时读哪个文件"即可。**每次调用少载入几 KB，17 个 workflow 天天跑，累积节省可观。**

### 第三档：谨慎投入（明确不建议现在做的）

| 项目 | 结论 | 理由 |
|---|---|---|
| 多 subagent 编排（reader/writer 隔离、单一 Write 持有者） | **暂缓** | Anthropic 的三层隔离（脏数据 reader 只读 + 严格 JSON schema、note-writer 独占写权限、委派深度 ≤1）设计漂亮，但每个 subagent 都是独立调用，成本翻倍。个人系统用 2.1 的代码门禁已能覆盖大部分风险。若将来做，只给 `/deep` 用，且抄"委派深度 ≤1 + 输出 schema 限长"两条。 |
| xlsx 财务模型产物 | **降级为 CSV** | 30-50 页 DOCX + 6 tab Excel + 25-35 张图是卖方研报交付标准，个人自用是过度工程。但"数字可复算、可 diff"的诉求成立：让估值脚本顺手落一个 `Reports/deepdive/*_model.csv`（假设、情景、敏感性），成本近零。 |
| hooks | **不投入** | Anthropic 自己的金融 plugin 里 `hooks.json` 全是空壳，质量控制全靠 skill 文本 + 脚本。 |
| 1000+ 行重型 SKILL | **不模仿** | dcf-model 1263 行是给通用 Claude 用户兜底的写法；AlphaSystem 有代码层（runner、门禁、工具），应把"确定性内容"放代码而非提示词。 |

---

## 3. 三角权衡总结

| 改动 | 时间投入 | LLM 成本变化 | 质量收益 |
|---|---|---|---|
| 2.1 门禁升级（填数字自检 + 硬否决） | 中（改 report_quality + 契约） | 0 | ★★★ |
| 2.2 估值脚本化 | 小 | ≈0（省口算轮次） | ★★★ |
| 2.3 toolbus 预算接线 | 小（代码已有） | **↓**（硬上限） | ★★ |
| 2.4 数据纪律三件套 | 小（改契约文本） | 0 | ★★ |
| 2.5 分档表 + NO SHORTCUTS | 小 | **↓**（禁额外产出） | ★★ |
| 2.6 双源合并 | 小 | 0 | ★（可维护性） |
| 2.7 深研两阶段 + critique | 中 | ↑ 每次深研 +1~2 次调用（但单次上下文变短） | ★★★ |
| 2.8 buy/sell 升 Pro | 极小 | ↑ 少量 | ★★★（高后果场景） |
| 2.9 workflow 瘦身分层 | 中 | **↓**（每次调用省数 KB 常驻） | ★★ |

**建议执行顺序：** 2.3 → 2.2 → 2.1 → 2.5 → 2.4 →（观察一段时间）→ 2.9 → 2.7/2.8 → 2.6。前五项合计不增加任何 LLM 调用（其中两项净降成本），先把"免费的质量"拿满，再考虑花钱买质量的 2.7/2.8。

---

## 落地记录

| 项 | 状态 | 落地位置 |
| :-- | :-- | :-- |
| 2.1 门禁升级 | ✅ 已实施 | `core/report_quality.py` 分档阈值 + 9 类新校验；`core/tool_factory.py` 按文件名推断档位 |
| 2.2 估值脚本化 | ✅ 已实施 | `scripts/valuation_math.py`；`deep/value/buy` 三个 workflow 强制调用 |
| 2.3 预算接线 | ✅ 已实施 | `settings.WorkflowBudgetSettings` 单一真理源；ToolFactory 工具层软门；WorkflowRunner 注入提示词 |
| 2.4 数据纪律 | ✅ 已实施 | `common/10-evidence-contract.md` 时效四步 + 缺失写法表 + 溯源即时化 |
| 2.5 分档表 + NO SHORTCUTS | ✅ 已实施 | `common/00-report-contract.md` |
| 2.6 双源合并 | ✅ 已实施 | `Skills/SKILL.md` 修复 4 个坏链接，标明与 `.agent/workflows/` 的主从关系 |
| 2.7 深研两阶段 + critique | ⏸ 待评估 | 需先观察分档门禁生效后 `/deep` 的实际通过率再决定 |
| 2.8 buy/sell 升 Pro | ✅ 已实施 | `settings.ModelRoutingSettings`，可用 `PRO_WORKFLOWS` 环境变量覆盖 |
| 2.9 workflow 瘦身分层 | ⏸ 待评估 | 改动面最大，建议独立一轮做 |

**附带修掉的既有缺陷（评审时发现，非清单内）**

- `write_to_file(mode='a')` 对片段单独送检，必然失败——等于禁止分段写入。
  改为校验「已有内容 + 追加内容」的最终文件状态，并移除 `Skills/SKILL.md` 里
  会把人引向该陷阱的分段写入指引。
- `common/20-quality-gate.md` 此前列出的 `report_date` / `evidence_table` /
  `ticker_match` / `live_tooling` / `price_provenance` 五项门禁在代码中并不存在。
  本轮把其中四项真正实现，并把该文档重写为「代码实际执行的门禁」表。

**验证**：全量测试 474 passed。`tests/test_models.py`（需真实 API key）与
`test_concurrency.py::test_bounded_at_max`（需 Telegram token）为环境相关的既有失败，
改动前后一致。

## 附：本次评审引用的关键原文位置

- 阶段化 + "一次只加载一个 reference"：`plugins/vertical-plugins/equity-research/skills/initiating-coverage/SKILL.md:704`
- 硬否决 + 填数字自检：`.../initiating-coverage/assets/quality-checklist.md`（`CRITICAL DO NOT DELIVER IF` / `Page count: ___ (MUST BE 30-50)`）
- 时效四步协议：`.../equity-research/skills/earnings-analysis/SKILL.md:119-128`
- 确定性校验脚本：`.../financial-analysis/skills/dcf-model/scripts/validate_dcf.py`（terminal growth < WACC 等；注意其孤儿化教训）
- NO SHORTCUTS 负面清单：`.../initiating-coverage/SKILL.md:75-85`
- 缺失数据 `-`/`[E]`/`[UNSOURCED]` 与口径标注：`.../financial-analysis/skills/competitive-analysis/SKILL.md`
- 三级加载规范（SKILL.md <500 行）：`anthropics/skills/skills/skill-creator/SKILL.md:88-98`
- subagent 契约与单一 Write 持有者：`managed-agent-cookbooks/earnings-reviewer/subagents/*.yaml`
