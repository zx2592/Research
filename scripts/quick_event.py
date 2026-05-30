import os
import sys
import argparse
from datetime import datetime
import time
# import yfinance as yf
# from brave_search import BraveSearchClient
# import google.generativeai as genai
from dotenv import load_dotenv
from kb_holdings import load_kb_context, load_holdings_context

# Path Setup
script_dir = os.path.dirname(os.path.abspath(__file__))
if "tools" in script_dir:
    project_root = os.path.dirname(os.path.dirname(script_dir))
else:
    project_root = os.path.dirname(script_dir)

if project_root not in sys.path:
    sys.path.append(project_root)

if script_dir not in sys.path:
    sys.path.append(script_dir)

load_dotenv(os.path.join(project_root, ".env"))

# genai.configure moved to generate_quick_report
if not os.getenv("GEMINI_API_KEY"):
    print("Error: GEMINI_API_KEY not found.")
    sys.exit(1)

def fetch_data(ticker):
    """Get basic info using Yahoo Finance WAF bypass and Tushare for A-shares."""
    print(f"📊 Fetching data for {ticker}...")
    
    # Check if it's an A-share
    is_a_share = ticker.endswith('.SS') or ticker.endswith('.SZ') or (ticker.isdigit() and len(ticker) == 6)
    tushare_name = None
    
    if is_a_share:
        try:
            import tushare as ts
            token = os.getenv("TUSHARE_TOKEN", "")
            if token:
                ts.set_token(token)
                pro = ts.pro_api()
                
                # Convert ticker format for Tushare
                ts_code = ticker
                if ts_code.endswith('.SS'):
                    ts_code = ts_code.replace('.SS', '.SH')
                elif ts_code.isdigit() and len(ts_code) == 6:
                    ts_code = f"{ts_code}.SH" if ts_code.startswith(('6', '9')) else f"{ts_code}.SZ"
                    
                df_basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,symbol,name')
                if not df_basic.empty:
                    tushare_name = df_basic.iloc[0]['name']
                    print(f"  ✅ Tushare hit: {tushare_name}")
        except Exception as e:
            print(f"⚠️ Tushare failed to fetch name: {e}")

    try:
        # Use Fast Fetch Bypass (KI: yahoo-finance-waf-bypass)
        from services.datahub.sources.yfinance_src import _fetch_price_via_urllib
        
        # Normalize ticker
        t_fixed = ticker
        if ticker.endswith(".SH"): t_fixed = ticker.replace(".SH", ".SS")
        elif ticker.endswith(".HK"):
            code = ticker.split('.')[0]
            t_fixed = f"{code.lstrip('0').zfill(4)}.HK"

        current_price = _fetch_price_via_urllib(t_fixed)
        
        # Try to get news and meta info using yfinance library as secondary/enrichment
        import yfinance as yf
        stock = yf.Ticker(t_fixed)
        
        if current_price is None:
            # Fallback for price only if urllib fails
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]

        # Get metadata (this is slow but provides sector/market cap)
        try:
            info = stock.info
        except:
            info = {}

        return {
            "symbol": ticker,
            "name": tushare_name if tushare_name else info.get("longName", ticker),
            "price": f"{current_price:.2f}" if current_price else "N/A",
            "change_amount": "N/A", # Speed priority: skip calculation in quick script
            "change_percent": "0.0%",
            "market_cap": info.get("marketCap", "N/A"),
            "pe": info.get("trailingPE", "N/A"),
            "sector": info.get("sector", "N/A"),
            "yf_news": stock.news[:5] if hasattr(stock, 'news') else []
        }
    except Exception as e:
        print(f"⚠️ Data fetch failed for {ticker}: {e}. Using fallback.")
        return {
            "symbol": ticker,
            "name": tushare_name if tushare_name else ticker,
            "price": "N/A", "change_amount": "N/A", "change_percent": "N/A",
            "market_cap": "N/A", "pe": "N/A", "sector": "N/A"
        }


def fetch_news(query, freshness=None):
    """Use Brave Search to find news."""
    print(f"🔍 Searching: {query} (Freshness: {freshness})...")
    try:
        import time
        from brave_search import BraveSearchClient
        time.sleep(1) 
        client = BraveSearchClient()
        data = client.search(query, count=20, freshness=freshness)
        return data.get("web", {}).get("results", [])
    except Exception as e:
        print(f"Search Error: {e}")
        return []

def generate_quick_report(data, event, news_items, analyst_views, kb_ctx="", holdings_ctx=""):
    """Synthesize Quick Report with LLMClient."""
    from core.llm_client import LLMClient
    print("🧠 Generating Quick Analysis...")
    client = LLMClient(force_mode="vps")
    
    context = ""
    # Add YFinance News
    if "yf_news" in data:
        for n in data["yf_news"]:
            context += f"- YF Headline: {n.get('content', {}).get('title')} ({n.get('content', {}).get('pubDate')})\n"
            
    for n in news_items:
        context += f"- News: {n.get('title')} ({n.get('url')}) - {n.get('description')}\n"
    for a in analyst_views:
         context += f"- Analyst View: {a.get('title')} ({a.get('description')})\n"
        
    prompt = f"""
    Role: Senior Equity Research Analyst.
    Task: Write a "Quick Event Comment" (事件快评) for {data['name']} ({data['symbol']}).
    Target Audience: Professional Investors.
    Language: Verified Simplified Chinese.
    
    **Event Input**: "{event}"
    
    **Market Data**:
    - Price: {data['price']} ({data['change_amount']}, {data['change_percent']})
    - PE: {data['pe']}

{holdings_ctx}
{kb_ctx}
    **IMPORTANT**: If knowledge base context is provided above, use it as baseline — focus your analysis on INCREMENTAL changes only. Do not repeat known background.
    
    **Context**:
    {context}
    
    **Report Format** (Follow this EXACTLY):
    
    # [YYYYMMDD] {data['symbol']} 事件快评

    > **事件：** [One sentence summary of event]
    > **信息级别：** Class A (Earnings/Data) / Class B (Rumor/Sentiment)
    > **核心判断：** Bullish / Bearish / Neutral
    > **逻辑影响：** 增强 / 削弱 / 无关
    
    ## 1. What — 发生了什么
    - [Objective facts about event]
    - [Key numbers if available]
    
    ## 2. Why — 为什么重要
    - [Strategic context]
    - [Impact on business model]
    
    ## 3. Impact — 边际影响
    - EPS 影响: ...
    - 估值传导: ...
    - 目标价影响: [无变化 / 上调 / 承压]
    
    ## 4. 局势与投资推演
    
    ### 核心玩家
    | 角色 | 标的 | 定性 |
    | :--- | :--- | :--- |
    | 赢家 | ... | ... |
    | 输家 | ... | ... |
    
    ### 投资推演
    - 长线确定性: ...
    - 短线情绪: ...
    - 观察指标: ...
    
    ## 5. 策略推演
    
    ### 长线护城河
    - 逻辑: [稳固 / 需重估]
    - 建议: ...
    
    ### 短线势能
    - 势能: [延续 / 衰竭 / 反转]
    - 建议: ...
    
    ## 6. 知识库更新摘要
    > [Key points to update in company profile]
    
    ---
    **生成模型**: Gemini Flash Latest (Stable)
    """
    
    response_text = client.chat(prompt, use_pro=False)
    return response_text.strip()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python quick_event.py [TICKER] [EVENT_DESCRIPTION]")
        sys.exit(1)
        
    ticker = sys.argv[1].upper()
    event = sys.argv[2] if len(sys.argv) > 2 else "Recent Major News"
    
    data = fetch_data(ticker)
    
    if data:
        # Load KB context and holdings status BEFORE searching
        print("📚 Loading knowledge base context...")
        kb_ctx       = load_kb_context(ticker)
        holdings_ctx = load_holdings_context(ticker)
        if kb_ctx:
            print(f"  ✅ KB hit for {ticker} — will use historical archive as baseline")
        else:
            print(f"  ℹ️  No KB entry for {ticker} — first analysis")
            
        # Smart Search Query Logic
        change_pct_str = data.get('change_percent', '0%').replace('%', '').replace('+', '')
        try:
            change_pct = float(change_pct_str)
        except ValueError:
            change_pct = 0.0

        # Detect A-share tickers for Chinese-language search
        is_a_share = ticker.endswith('.SZ') or ticker.endswith('.SS') or ticker.endswith('.SH')
        cn_name = data.get('name', ticker)  # Chinese name from Tushare if available

        if len(sys.argv) > 2:
            query_event = f"{ticker} {event} impact analysis"
            query_analyst = f"{ticker} {event} analyst rating target price"
            queries = [query_event, query_analyst]
            # A股追加中文搜索
            if is_a_share and cn_name != ticker:
                queries.append(f"{cn_name} {event} 最新消息 业绩 公告")
        else:
            if change_pct <= -3.0:
                print(f"📉 Detected significant drop ({change_pct}%). Searching for reasons...")
                event = "stock price dropped significantly"
                if is_a_share and cn_name != ticker:
                    queries = [
                        f'{cn_name} 股价下跌 原因 利空',
                        f'{cn_name} 业绩 公告 最新消息 2026',
                    ]
                else:
                    queries = [
                        f'"{ticker}" stock drop news OR "why is {ticker} down"',
                        f'"{ticker}" OR "{cn_name}" competitor pricing market share threat',
                        f'"{ticker}" bear case OR "{ticker}" short thesis OR "{ticker}" downgrade reason'
                    ]
            elif change_pct >= 3.0:
                print(f"📈 Detected significant surge ({change_pct}%). Searching for reasons...")
                event = "stock price surged significantly"
                if is_a_share and cn_name != ticker:
                    queries = [
                        f'{cn_name} 股价上涨 利好 原因',
                        f'{cn_name} 业绩预告 公告 最新消息 2026',
                    ]
                else:
                    queries = [
                        f'"{ticker}" stock surge news OR "why is {ticker} up"',
                        f'"{ticker}" upgrade OR analyst price target raise'
                    ]
            else:
                event = "Recent Major News and Catalysts"
                if is_a_share and cn_name != ticker:
                    queries = [
                        f'{cn_name} 最新消息 业绩预告 公告 2026',
                        f'{cn_name} 研报 目标价 评级',
                    ]
                else:
                    queries = [
                        f'"{ticker}" stock news catalyst',
                        f'"{ticker}" analyst rating target price'
                    ]
        
        # Aggregate search results
        all_news = []
        for i, q in enumerate(queries):
            if i > 0:
                time.sleep(3) # Wait between queries to avoid rate limits
            results = fetch_news(q, freshness="pw")
            all_news.extend(results)
        
        # Deduplicate and sort by something if possible, but keep simple for now
        report = generate_quick_report(data, event, all_news, [], # Merge all into one context
                                       kb_ctx=kb_ctx, holdings_ctx=holdings_ctx)
        
        # Save Report
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{timestamp}_{ticker}_Quick.md"
        
        reports_dir = os.path.join(project_root, "Reports", timestamp)
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        filepath = os.path.join(reports_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
            
        print(f"✅ Report saved: {filepath}")
        
        # Sync
        try:
            import sync_to_obsidian
            sync_to_obsidian.sync_reports()
            print("✅ Synced to Obsidian.")
        except Exception as e:
            print(f"⚠️ Obsidian Sync Failed: {e}")
            try:
                sys.path.append(script_dir)
                import sync_to_obsidian
                sync_to_obsidian.sync_reports()
            except:
                pass
