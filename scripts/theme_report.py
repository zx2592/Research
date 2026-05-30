"""
A-Share Momentum × Theme × Volatility System
Tushare Pro 全接口版（含 THS 同花顺概念板块数据）
AUM=200万、目标年化波动20%
"""
import subprocess
import sys
import json
import datetime
import os

TOKEN = '19c987d6bec43d74a9eac6e866caf15898cc5c044ed8d1698cf47c25'
AUM = 2000000
TARGET_VOL = 0.20
W_MAX = 0.10
ADV20_THRESHOLD = max(50000000, 50 * AUM * W_MAX)

def ts_call(code, timeout=20):
    """Run any tushare snippet in a subprocess with timeout, returns stdout string."""
    script = f"""
import tushare as ts, json, sys, warnings
warnings.filterwarnings('ignore')
ts.set_token('{TOKEN}')
pro = ts.pro_api()
{code}
"""
    try:
        r = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True, timeout=timeout
        )
        out = r.stdout.decode('gbk', errors='replace').strip() if r.stdout else ''
        err = r.stderr.decode('gbk', errors='replace').strip() if r.stderr else ''
        if r.returncode == 0:
            return out, None
        else:
            return None, err[:300]
    except subprocess.TimeoutExpired:
        return None, 'TIMEOUT'
    except Exception as e:
        return None, str(e)


# ============================
# Step 0: Resolve latest trade date & HS300
# ============================
today_str = datetime.datetime.now().strftime("%Y-%m-%d")
print("=== A-Share Real-Time Checklist ===")

trade_date = None
regime = "Range (震荡市)"
realized_vol = 0.20
scale = 1.0
total_exposure = 0.6

for i in range(7):
    d = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%Y%m%d')
    out, err = ts_call(f"""
import pandas as pd, numpy as np, datetime
df = pro.daily(trade_date='{d}', limit=5)
if not df.empty:
    print('{d}', len(df))
""", timeout=20)
    if out and d in out:
        trade_date = d
        print(f"  Latest trade date: {trade_date}")
        break

if not trade_date:
    trade_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y%m%d')

# Regime via HS300
past_start = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime('%Y%m%d')
regime_out, _ = ts_call(f"""
import pandas as pd, numpy as np
hs300 = pro.index_daily(ts_code='000300.SH', start_date='{past_start}', end_date='{trade_date}')
hs300 = hs300.sort_values('trade_date')
closes = hs300['close'].values
if len(closes) >= 60:
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:])
    cur = closes[-1]
    ret = np.diff(closes[-21:])/closes[-21:-1]
    rvol = np.std(ret)*np.sqrt(250)
    if cur > ma60 and ma20 > ma60 and rvol < 0.25:
        mode = 'Trend'
    elif cur < ma60 and (rvol > 0.25 or ma20 < ma60):
        mode = 'Risk'
    else:
        mode = 'Range'
    cap = {{'Trend':1.0, 'Range':0.6, 'Risk':0.2}}[mode]
    scale = min(max({TARGET_VOL}/(rvol+0.01), 0.25), 1.0)
    print(mode, round(rvol*100,1), round(cap, 2), round(scale, 2))
""")

if regime_out:
    parts = regime_out.split()
    if len(parts) >= 4:
        mode_map = {'Trend': 'Trend (趋势市)', 'Range': 'Range (震荡市) - 轮动思路', 'Risk': 'Risk (风险市) - 防守配置'}
        regime = mode_map.get(parts[0], 'Range (震荡市)')
        realized_vol = float(parts[1]) / 100
        cap = float(parts[2])
        scale = float(parts[3])
        total_exposure = cap * scale

print(f"  Regime: {regime} | Vol: {realized_vol*100:.1f}% | Exposure: {total_exposure*100:.1f}%")

# ============================
# Step 1: THS Concept Board Rankings
# ============================
print("  Fetching THS concept board rankings...")

ths_out, ths_err = ts_call(f"""
import pandas as pd

# Get list of all THS concept indexes
idx = pro.ths_index(exchange='A', type='N')
# Filter to concept-level (not sample indexes)
concepts = idx[idx['ts_code'].str.startswith('885')].head(80)

# Fetch today's daily returns for concepts concurrently
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_single_concept(row):
    try:
        import tushare as ts
        local_pro = ts.pro_api()
        daily = local_pro.ths_daily(ts_code=row['ts_code'], start_date='{trade_date}', end_date='{trade_date}')
        if not daily.empty:
            d = daily.iloc[0]
            pct = round((d['close'] - d['pre_close']) / d['pre_close'] * 100, 2) if d['pre_close'] else 0
            return {{'name': row['name'], 'pct_chg': pct, 'vol': d.get('vol', 0)}}
    except:
        pass
    return None

rows = []
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [executor.submit(fetch_single_concept, row) for _, row in concepts.iterrows()]
    for future in as_completed(futures):
        res = future.result()
        if res:
            rows.append(res)

if rows:
    df = pd.DataFrame(rows).sort_values('pct_chg', ascending=False)
    print(df.head(12).to_json(orient='records', force_ascii=False))
""", timeout=40)

theme_rows = ""
top_board_names = []

if ths_out and ths_out.startswith('['):
    try:
        boards = json.loads(ths_out)
        for i, b in enumerate(boards[:10]):
            name = b['name']
            chg = b['pct_chg']
            top_board_names.append(name)
            if chg > 5:
                status, warn = '主线升浪', '否'
            elif chg > 2:
                status, warn = '资金流入', '否'
            elif chg > 0:
                status, warn = '震荡企稳', '否 (需观察)'
            else:
                status, warn = '调整中', '是'
            theme_rows += f"| {i+1} | **{name}** | {chg:+.2f}% | {status} | {warn} |\n"
        print(f"  THS themes OK: {len(boards)} concepts fetched")
    except Exception as e:
        print(f"  THS parse error: {e}")

if not theme_rows:
    theme_rows = "| - | THS概念板块数据请求超时，建议检查网络或稍后重试 | N/A | N/A | N/A |\n"

# ============================
# Step 2-3: Momentum Stock Candidates
# ============================
print("  Fetching momentum stock candidates...")

stocks_out, _ = ts_call(f"""
import pandas as pd, json

# Fetch today's full market daily and daily_basic
df = pro.daily(trade_date='{trade_date}')
df_basic = pro.daily_basic(trade_date='{trade_date}', fields='ts_code,turnover_rate,circ_mv')
df = pd.merge(df, df_basic, on='ts_code', how='inner')

df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
df['amount'] = pd.to_numeric(df['amount'], errors='coerce') * 1000
df['turnover_rate'] = pd.to_numeric(df['turnover_rate'], errors='coerce')
df['circ_mv'] = pd.to_numeric(df['circ_mv'], errors='coerce') * 10000  # Convert to actual RMB

# Get stock basics for names/industry
basics = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,industry')
df = pd.merge(df, basics, on='ts_code')

# Apply Hard Filters (PSMV: No Limit-Ups, Liquidity threshold, No ST/BJ)
mask = (
    ~df['name'].str.contains('ST') &
    df['ts_code'].str.endswith(('SZ', 'SH')) &
    (df['amount'] > {ADV20_THRESHOLD}) &
    (df['pct_chg'] > -1.0) & 
    (df['pct_chg'] <= 7.5)  # PSMV Rule: Dont chase limit-ups, find continuation
)
candidates = df[mask].copy()

# Calculate Swift PSMV Score (Max 10)
def calc_psmv(row):
    score = 0
    
    # 1. Market Cap (Max 3 points)
    mv = row.get('circ_mv', 0)
    if 50e8 <= mv <= 300e8:
        score += 3.0
    elif (30e8 <= mv < 50e8) or (300e8 < mv <= 1000e8):
        score += 1.5
        
    # 2. Turnover (Max 3 points)
    turnover = row.get('turnover_rate', 0)
    if 5.0 <= turnover <= 15.0:
        score += 3.0
    elif 15.0 < turnover <= 25.0:
        score += 1.5
    # >25% or <3% gets 0 points
    
    # 3. Daily Momentum (Max 4 points)
    pct = row.get('pct_chg', 0)
    if 4.0 <= pct <= 7.5:
        score += 4.0
    elif 1.0 <= pct < 4.0:
        score += 2.0
    
    return min(score, 10.0)

candidates['psmv_score'] = candidates.apply(calc_psmv, axis=1)

# Sort by PSMV Score descending, then by pct_chg
result = candidates.sort_values(['psmv_score', 'pct_chg'], ascending=[False, False]).head(10)
print(result[['symbol','name','industry','pct_chg','amount','turnover_rate','circ_mv','psmv_score']].to_json(orient='records', force_ascii=False))
""", timeout=30)

trade_list_rows = []
top_stocks = []
if stocks_out and stocks_out.startswith('['):
    try:
        stocks = json.loads(stocks_out)
        top_stocks = stocks[:4]
        for s in top_stocks:
            theme = top_board_names[len(trade_list_rows)-1] if len(trade_list_rows)-1 < len(top_board_names) else s.get('industry','强势股')
            code = s['symbol']
            name = s['name']
            chg = s['pct_chg']
            score = s.get('psmv_score', 0)
            tr = s.get('turnover_rate', 0)
            mv_b = s.get('circ_mv', 0) / 1e8
            
            trade_list_rows.append(
                f"| {code} | {name} | {theme} | {chg:+.2f}% | **{score:.1f}** | {tr:.1f}% | {mv_b:.0f}亿 | {W_MAX*100:.0f}% |"
            )
        print(f"  Stocks OK: {len(stocks)} candidates found")
    except Exception as e:
        print(f"  Stocks parse error: {e}")

trade_list = "\n".join(trade_list_rows)

# ============================
# Report Output
# ============================
md = f"""# 📊 A-Share 动量×主题×波动 盘前清单 (Tushare Pro + THS实盘版)
*交易日：{trade_date} | 资金规模：{AUM/10000:.0f}万 | 目标年化波动：{TARGET_VOL*100:.0f}%*

---

## 01 大势研判与仓位管理

| 参数 | 数值 |
| :--- | :--- |
| **当前 Regime** | `{regime}` |
| **近期实现波动率 (20D)** | {realized_vol*100:.1f}% |
| **波动率缩放因子** | {scale:.2f} |
| **建议总仓位上限 TotalExposure** | **{total_exposure*100:.1f}%** |
| **回撤刹车等级** | Level 0 (未触发) |

---

## 02 同花顺 THS 概念板块热度榜

*数据来源：Tushare Pro `ths_daily` | 交易日：{trade_date}*

| 排名 | 概念板块 | 日内涨跌幅 | 形态研判 | 退潮预警 |
| :--- | :--- | :--- | :--- | :--- |
{theme_rows}

---

## 03 动量候选标的 (Swift PSMV V2.1)

> **核心逻辑**：不追涨停板，寻找上升中继。过滤极端体量被控盘与流动性枯竭标的。  
> **市值甜点区**：50亿-300亿 | **换手甜点区**：5%-15%  
> **单票最大仓位**：{W_MAX*100:.0f}% (≈ {AUM*W_MAX/10000:.0f}万)

### 🟢 开仓/加仓观察池

| 代码 | 名称 | 归属主题 | 日内涨跌 | PSMV得分 | 换手率 | 流通市值 | 建议仓位 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 510300 | 沪深300ETF | 宽基基础 | - | N/A | - | - | 15% |
{trade_list}

### 🔴 减仓/离场

*   持仓跌破 20 日均线且满足 `EntryPrice - 2.5×ATR` 止损条件 → 无条件离场。
*   今日出现在跌幅板块的持仓 → 观察缩量情况，冲高减仓 50%。

---

## 04 风控纪律

1. **T+1 届满摩擦**：今日买入次日方可卖出，避免冲高追高后被套。  
2. **涨跌停排队风险**：热度极高的连板标的慎追，排队成本可能吃掉利润。  
3. **刹车线**：若组合从峰值回撤 ≥ 8%，总仓位上限强制降至 {total_exposure*0.7*100:.1f}%。
"""

# Determine project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Save to dated folder
date_dir = os.path.join(PROJECT_ROOT, "Reports", trade_date)
os.makedirs(date_dir, exist_ok=True)
out_path = os.path.join(date_dir, f"{trade_date}_A_Share_Real_Time_Checklist.md")
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(md)

# Also keep in today's folder
today_str = datetime.datetime.now().strftime('%Y%m%d')
today_dir = os.path.join(PROJECT_ROOT, "Reports", today_str)
os.makedirs(today_dir, exist_ok=True)
out_path2 = os.path.join(today_dir, f"{today_str}_A_Share_Real_Time_Checklist.md")
with open(out_path2, 'w', encoding='utf-8') as f:
    f.write(md)

print(f"\n  Report saved to: {out_path}")
print("=== Done ===")
