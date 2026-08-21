---
name: Time Zone Context
description: Critical time zone and market hours context for this user to prevent "future date" errors
---

> **契约例外（纯流程）**：本工作流产出的是**时间上下文片段**，不是决策报告——公共报告契约的八章节结构不适用。仍然适用的是：时间必须取网络校准时间，**不得凭训练记忆写日期**。

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


# Time Zone Context Skill

## Critical Information

### User Location & Time Settings

**Physical Location**: 美国西海岸 (US West Coast)
**System Time**: 北京时间 (Beijing Time, UTC+8)
**Reason**: 为了与 A 股市场时间保持一致

### Time Conversion Rules

当系统显示北京时间时：
- **北京时间 02:00** = **美西时间 前一天 10:00**
- **时差**: 北京时间领先美西时间 **16 小时**（冬令时）或 **15 小时**（夏令时）

### Market Hours (Beijing Time)

| 市场 | 交易时间 (北京时间) | 对应美西时间 |
|:---|:---|:---|
| **A股/港股** | 09:30 - 15:00 | 前一天 17:30 - 23:00 |
| **美股** | 22:30 - 05:00 (次日) | 06:30 - 13:00 (当天) |
| **日股** | 08:00 - 14:00 | 前一天 16:00 - 22:00 |
| **大宗商品** | 24/7 | 24/7 |
| **加密货币** | 24/7 | 24/7 |

## Common Pitfalls to Avoid

### ❌ 错误示例
```
系统时间: 2026-01-31 02:00 (北京时间)
错误判断: "这是未来日期，没有数据"
```

### ✅ 正确理解
```
系统时间: 2026-01-31 02:00 (北京时间)
实际情况: 
- 美西时间: 2026-01-30 10:00
- 美股市场: 正在交易中
- 大宗/加密: 24/7 交易中
- 数据完全可用
```

## Data Availability Rules

### 1. 实时数据可用性

**北京时间 22:00 - 次日 05:00**:
- ✅ 美股实时数据
- ✅ 大宗商品实时数据
- ✅ 加密货币实时数据
- ❌ A股/港股（休市）

**北京时间 09:00 - 16:00**:
- ✅ A股/港股实时数据
- ✅ 大宗商品实时数据
- ✅ 加密货币实时数据
- ❌ 美股（休市）

**周末 (北京时间)**:
- ❌ 股票市场（全球休市）
- ✅ 大宗商品（部分交易）
- ✅ 加密货币（24/7）

### 2. 特殊情况

**北京时间周六凌晨 00:00 - 05:00**:
- 对应美西时间**周五下午**
- 美股**仍在交易**
- 不要误判为"周末无数据"

## Action Guidelines

### When User Provides Market Data

1. **不要质疑时间**
   - 用户提供的数据通常是实时的
   - 系统时间显示"未来"是正常的（北京时间领先）

2. **验证数据来源**
   - 通过 yfinance/API 验证价格
   - 不要因为"未来日期"就认为数据无效

3. **市场时段判断**
   - 根据北京时间判断哪些市场开盘
   - 参考上述"Market Hours"表格

### When Searching for News

**搜索策略**:
- 使用"today"而非具体日期
- 使用"latest"、"current"等关键词
- 避免使用系统日期作为搜索条件

**示例**:
```
❌ "silver crash January 30 2026"
✅ "silver crash today latest news"
✅ "silver futures flash crash current"
```

## Implementation in Code

### market_sentinel.py

```python
# 已正确实现：使用 pytz 处理北京时间
beijing_tz = pytz.timezone('Asia/Shanghai')
now = datetime.now(beijing_tz)

# 判断市场开盘时使用北京时间
# 美股: 22:30 - 05:00 (北京时间)
# A股: 09:30 - 15:00 (北京时间)
```

### 数据获取

```python
# 正确：不依赖日期判断，直接获取最新数据
ticker = yf.Ticker("SI=F")
hist = ticker.history(period="1d")  # 获取最近一天
current_price = hist['Close'].iloc[-1]
```

## Summary

**核心原则**: 
1. 系统时间 = 北京时间（领先美西 15-16 小时）
2. 用户在美西，数据是实时的
3. 不要因为"未来日期"就质疑数据有效性
4. 根据北京时间判断市场开盘状态

---

**创建日期**: 2026-01-31  
**重要性**: 🔴 Critical - 防止时间判断错误
