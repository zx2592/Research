# 公共质量门禁

## 保存前硬门槛

在调用 `write_to_file` 保存 `Reports/**/*.md` 之前，必须先把完整 Markdown 报告传入：

```text
check_report_quality(markdown, filename)
```

**`filename` 要带上**（即准备写入的报告路径）。阈值按报告档位不同：`/deep` 要 6 行证据、
`/quick` 要 2 行。不带 filename 时按最宽松档校验，会出现「自检显示通过、落盘却被拒」。

如果返回 `passed: false`：

1. 不得保存报告。
2. 必须根据 `missing_sections` 和 `issues` 补齐内容。
3. 再次调用 `check_report_quality`。
4. 只有通过后才能调用 `write_to_file`。

`write_to_file` 对 `Reports/**/*.md` 已启用硬门禁：不合格报告会被拒绝写入，返回 `Report quality gate failed: {...}`。**按返回的清单逐项改完重新保存，不要换个说法重投。**

## 绝不交付：命中任一条直接重做

以下情况不是「扣分项」，是**不合格交付**。发现后先修，不要带着它落盘：

- ❌ 章节只有标题没有正文，或写着 `TBD` / `待补充` / `N/A` 占位
- ❌ 证据台账只有表头没有数据行
- ❌ 整轮一次真实取证都没有，全凭训练记忆写成
- ❌ 价格未交叉却给了目标价 / 止损 / 盈亏比
- ❌ 报告写的是 A 股票，文件名是 B 股票
- ❌ 自检里报的证据行数与正文实际行数对不上
- ❌ 与历史报告结论反转却没有 `## 冲突解释`

## 质量 Gate 8 问（填数字，不要打勾）

任一不过 → 先修正；无法修正 → 在「风险与不确定性 / 证据缺口」如实标注，不得跳过或粉饰。

「是否完整」可以自我安慰，「几行」不能。所以自检要求填**实际计数**，代码会拿它和正文对账：

```
- 证据台账行数: ___        （深研 ≥6 / 决策 ≥5 / 扫描 ≥3 / 快评 ≥2）
- 其中反方 (Bear) 证据行数: ___   （必须 ≥1）
- 联网取证次数: ___        （必须 ≥1；为 0 则报告不得落盘）
- 标注 [UNSOURCED] 的判断数: ___  （越多越说明本轮取证不足）
```

1. 有无引用**过期数据**（无时间戳即视为过期）？
2. 有无**只给结论没给证据**？
3. 有无**数字无源**？
4. 有无**把新闻观点当事实**（T3 当 T1 用）？
5. 有无**遗漏反方 (Bear)**？
6. **行动建议能执行吗**（含仓位 / 价格 / 时间窗）？
7. **说明了看错怎么办**（失效条件 / 退出信号）？
8. **价格证据交叉了吗**——结论先行区是否有 `价格证据：…` 一行，写明层级与交叉与否？

报告末尾盖印章：`✅ 质量Gate 8/8` 或 `⚠️ N/8，未过项见风险与不确定性`。

## 代码实际执行的门禁

下表每一项都由 `core/report_quality.py` 真正校验，返回的 `issues` 用的就是这些标识符。
**这张表描述的是已实现的行为，不是待办清单**——读到什么就会被拦到什么。

| `issues` 标识 | 不合格条件 |
| --- | --- |
| `missing_top_level_title` | 报告不以 `#` 开头 |
| `missing_sections` | 缺结论先行 / 实时数据快照 / 证据台账 / Bull-Base-Bear / 行动计划 / 风险与不确定性 / 质量自检 任一章节 |
| `empty_sections` | 章节有标题但正文为空或只有占位符（同时列在 `thin_sections`） |
| `report_below_tier_minimum` | 篇幅低于本档下限（深研 4000 / 决策 2000 / 扫描 1500 / 快评 600 字符） |
| `evidence_table_has_no_rows` | 证据台账没有表格数据行（只有表头不算） |
| `evidence_rows_below_tier_minimum` | 证据行数低于本档下限 |
| `evidence_missing_bear_row` | 证据台账里没有任何一行是反方证据 |
| `missing_explicit_date` | 全篇找不到 `YYYY-MM-DD` 或 `YYYYMMDD` 形态的日期 |
| `missing_source_reference` | 全篇没有 URL / `来源` / `出处` / `fetched_at` |
| `missing_live_tooling_evidence` | 工具层记录到的真实取证次数为 0（`get_evidence_log()` 可查）。未启用记录时退回正文正则：找不到 `fetched_at` / `verdict` / `cross_validate` / `consensus_price` 等痕迹 |
| `missing_two_sided_view` | 全篇没有反方（Bear / 空方）表述 |
| `price_commitment_without_provenance` | 出现目标价 / 止损 / 盈亏比，却没有价格交叉验证记录 |
| `ticker_mismatch` | 正文没出现文件名标注的标的 |
| `self_check_counts_missing` | 深研 / 决策档没在自检里填出计数 |
| `self_check_count_mismatch` | 自检申报的证据行数与正文实际行数对不上 |
| `unexplained_conflict_with_prior_report` | 与历史报告冲突但缺 `## 冲突解释`（见下） |

返回结果还带三个**参考字段**（不直接判不合格，但会被记录）：`evidence_row_count`（实际证据行数）、
`unsourced_claims`（`[UNSOURCED]` 标记数）、`tier`（本次按哪一档校验）、
`recorded_fetches`（工具层记录到的真实取证次数）。

价格如实申报为单源**不拒收**——但按报告契约，这时一律不给目标价 / 止损 / 盈亏比；
给了就会命中 `price_commitment_without_provenance`。

## 历史报告冲突门禁

当本次报告与同一标的的同日或近期历史报告存在以下冲突时，必须新增 `## 冲突解释` 章节：

- 动作建议从 `买入 / 逢低买入 / 持有 / 看多` 变成 `驳回 / 拒绝买入 / 不买入`，或反向变化。
- 核心商品、行业 Beta 或关键催化方向反转，例如 `钨价上涨/连涨/飙升` 变成 `钨价下跌/回落/腰斩/崩塌`。
- 同一关键数据出现明显不同口径，例如价格、估值、52周区间、利润预测、行动价。

`冲突解释` 必须说明：

1. 冲突来自哪一份历史报告。
2. 哪些结论或证据发生变化。
3. 新证据的来源、日期和可靠性等级。
4. 为什么新证据足以覆盖旧结论。

如果存在冲突但没有解释，`write_to_file` 会拒绝保存报告。
