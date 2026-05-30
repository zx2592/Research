# AlphaSystem V3.1 — Phase 7 主动智能功能使用指南

> **生成日期**: 2026-03-10  
> **适用版本**: V3.1 (Phase 7)  
> **前提条件**: `.env` 中已配置 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`GEMINI_API_KEY`

---

## 功能概览

Phase 7 新增了三个**主动推送**功能，让系统在你不主动提问的情况下，自动把关键情报送到你的手机。

| 功能 | 脚本 | 触发时机 | Telegram 快捷命令 |
|:---|:---|:---|:---|
| 🌅 晨报推送 | `scripts/morning_scan_push.py` | 工作日 08:00 | `/morning` |
| 📅 财报日历提醒 | `scripts/earnings_reminder.py` | 每周日 09:00 | `/earnings` |
| 📊 持仓周报 | `scripts/weekly_position_report.py` | 每周五 18:00 | `/weekly` |

---

## 一键启用自动推送（推荐）

以**管理员身份**运行以下脚本，自动注册全部三个 Windows 定时任务：

```bat
:: 右键 → 以管理员身份运行
scheduler.bat
```

验证任务是否创建成功：
```powershell
schtasks /query /tn "AlphaSystem*"
```

如需删除/修改任务：
```powershell
schtasks /delete /tn "AlphaSystem_MorningPush" /f
schtasks /delete /tn "AlphaSystem_EarningsReminder" /f
schtasks /delete /tn "AlphaSystem_WeeklyReport" /f
```

---

## 功能详解

### 🌅 晨报自动推送 (7.3)

**作用**：每天自动把当日市场全景扫描报告（由 `/scan` 生成）的核心段落推送到 Telegram。

**推送内容**：
- 市场体温（Risk On / Off）
- 一句话摘要
- 持仓预警表格
- 前 3 条风险提示

**依赖**：当天必须已有 `/scan` 生成的报告文件（`Reports/YYYYMMDD/YYYYMMDD_Market_Scan.md`），否则脚本会跳过推送。

> [!TIP]
> **最佳实践**：将 `/scan` 脚本设置在 07:30 运行，晨报推送设在 08:00，保证报告已生成。

**手动测试（命令行）**：
```bash
# 在 research/ 目录下执行
python scripts/morning_scan_push.py

# 指定日期（如推送昨天的报告）
python scripts/morning_scan_push.py --date 20260309
```

**手动测试（Telegram Bot）**：
```
/morning
```

---

### 📅 财报日历提醒 (7.2)

**作用**：每周日扫描你的全部持仓，找出**未来 7 天内有财报**的标的，提前推送提醒。

**推送示例**：
```
📅 【财报日历提醒】
2026-03-10 周报 — 未来 7 天财报预警

🚨 NVDA  财报日：2026-03-12 (2 天后)
⏰ GOOG  财报日：2026-03-15 (5 天后)

💡 建议：提前执行 /radar [Ticker] 生成财报预检。
```

**手动测试（命令行）**：
```bash
python scripts/earnings_reminder.py

# 调整提前天数（默认 7 天）
python scripts/earnings_reminder.py --days 14
```

**手动测试（Telegram Bot）**：
```
/earnings
```

> [!NOTE]
> 数据来源为 yfinance，部分 A 股 / 港股标的财报日信息可能缺失，以实际推送为准。

---

### 📊 持仓周报 (7.4)

**作用**：每周五收盘后，自动计算本周每个持仓的涨跌幅，并用 Gemini AI 生成一段简短的组合健康度分析，推送到 Telegram。

**推送示例**：
```
📊 【AlphaSystem 持仓周报 · 2026-03-10】

  🟢 NVDA：+10.00%
  🟢 8888.HK：+5.20%
  🔴 601975.SH：-2.30%

📝 AI 分析:
本周组合整体跑赢大盘，NVDA 受 AI 算力需求超预期推动大幅领先。
油运板块小幅分化，下周关注 VLCC 运费走势及中东局势进展。

💡 如需深度诊断，请执行 /position。
```

**手动测试（命令行）**：
```bash
python scripts/weekly_position_report.py

# 指定持仓文件
python scripts/weekly_position_report.py --holdings Config/holdings.json
```

**手动测试（Telegram Bot）**：
```
/weekly
```

---

## Telegram Bot 新命令汇总

Bot 已同步更新（V3.0），`/start` 或 `/help` 可查看完整命令列表：

| 命令 | 功能 |
|:---|:---|
| `/morning` | 立即推送今日晨报摘要 |
| `/earnings` | 立即检查持仓财报日历 |
| `/weekly` | 立即生成并推送持仓周报 |

---

## 故障排查

| 现象 | 可能原因 | 解决方法 |
|:---|:---|:---|
| 晨报没有推送 | 当天没有 Market_Scan 报告 | 先手动执行 `/scan` |
| 财报提醒没有消息 | 持仓标的未来 7 天无财报 | 正常现象，无需操作 |
| 周报 Gemini 报错 | `GEMINI_API_KEY` 未配置 | 检查 `.env` 文件 |
| Telegram 收不到消息 | Bot Token 或 Chat ID 有误 | 运行 `python core/notifier.py` 测试推送 |
| 定时任务未触发 | 计划任务未以管理员注册 | 重新管理员运行 `scheduler.bat` |

---

## 运行要求

```
python >= 3.12
yfinance >= 0.2
google-genai  (新版 SDK)
python-telegram-bot
python-dotenv
```
