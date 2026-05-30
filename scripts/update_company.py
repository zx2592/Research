import os
import sys
import argparse
from datetime import datetime
import time
import yfinance as yf
from brave_search import BraveSearchClient
from google import genai
from dotenv import load_dotenv
from kb_holdings import load_kb_context, load_holdings_context

# Path Setup
script_dir = os.path.dirname(os.path.abspath(__file__))
# Check if running from nested tools dir or root
if "tools" in script_dir:
    project_root = os.path.dirname(os.path.dirname(script_dir)) # Research/
else:
    project_root = os.path.dirname(script_dir)

# Add tools to path for sync_to_obsidian import
if script_dir not in sys.path:
    sys.path.append(script_dir)

load_dotenv(os.path.join(project_root, ".env"))

# AI Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY, vertexai=False)
else:
    print("Error: GEMINI_API_KEY not found.")
    sys.exit(1)

GEMINI_MODEL = "gemini-flash-latest"


def _parts_to_text(parts):
    if not parts:
        return None

    chunks = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)

    return "".join(chunks) if chunks else None


def _extract_response_text(response):
    if hasattr(response, "parts") and response.parts:
        text = _parts_to_text(response.parts)
        if text:
            return text

    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None)
            text = _parts_to_text(parts)
            if text:
                return text

    try:
        return response.text
    except Exception:
        return ""


def fetch_data(ticker):
    """Get basic info from yfinance."""
    print(f"馃搳 Fetching data for {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        # Force a history call to check validity
        hist = stock.history(period="5d")
        if hist.empty:
            return None

        info = stock.info
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price

        # Calculate price changes
        change_amount = current_price - prev_close
        change_percent = (change_amount / prev_close * 100) if prev_close != 0 else 0

        return {
            "symbol": ticker,
            "name": info.get("longName", ticker),
            "price": f"{current_price:.2f}",
            "change_amount": f"{change_amount:+.2f}",
            "change_percent": f"{change_percent:+.2f}%",
            "market_cap": info.get("marketCap", "N/A"),
            "pe": info.get("trailingPE", "N/A"),
            "forward_pe": info.get("forwardPE", "N/A"),
            "peg_ratio": info.get("pegRatio", "N/A"),
            "sector": info.get("sector", "N/A")
        }
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def fetch_news(query, freshness=None):
    """Use Brave Search to find news."""
    print(f"馃攳 Searching: {query} (Freshness: {freshness})...")
    try:
        time.sleep(1) # Rate limit protection
        client = BraveSearchClient()
        # count=8 to get more candidates
        data = client.search(query, count=10, freshness=freshness)
        # Extract list from data
        return data.get("web", {}).get("results", [])
    except Exception as e:
        print(f"Search Error: {e}")
        return []


def generate_report(data, news_items, earnings_items, breaking_news, kb_ctx="", holdings_ctx=""):
    """Synthesize report with Gemini."""
    print("馃 Generating Analysis...")

    context = ""
    for n in news_items:
        context += f"- News: {n.get('title')} ({n.get('url')}) - {n.get('description')}\n"
    for e in earnings_items:
        context += f"- Earnings/Guidance: {e.get('title')} ({e.get('url')}) - {e.get('description')}\n"
    for b in breaking_news:
         context += f"- BREAKING (Today/Recent): {b.get('title')} ({b.get('description')}) ({b.get('url')})\n"

    prompt = f"""
    Role: Senior Equity Research Analyst.
    Task: Write a structured "Company Update" report for {data['name']} ({data['symbol']}).
    **CRITICAL INSTRUCTION: THE ENTIRE REPORT MUST BE WRITTEN IN SIMPLIFIED CHINESE.**

    **Market Data (VERIFIED - Use this as ground truth)**:
    - Current Price: {data['price']}
    - Price Change: {data['change_amount']} ({data['change_percent']})
    - Trailing PE: {data['pe']}
    - Forward PE: {data['forward_pe']}
    - PEG Ratio: {data['peg_ratio']}
    - Sector: {data['sector']}

{holdings_ctx}
{kb_ctx}
    **IMPORTANT**: If knowledge base context is provided above, treat it as historical baseline. In your report, focus on incremental changes since that baseline. Annotate report with 馃摎 if using historical context, or 馃啎 if first analysis.

    **Information Sources**:
    {context}

    **CRITICAL INSTRUCTION**:
    - The Market Data above shows the ACTUAL price change.
    - If news headlines claim "stock soared 7%" but Market Data shows negative change, you MUST state that the gains were erased or the stock closed lower.
    - DO NOT simply repeat news headlines about price movements. ALWAYS verify against Market Data.
    - If there's a discrepancy, explain it (e.g., "opened higher but closed lower").

    **WRITING STYLE REQUIREMENTS**:
    - PRIORITIZE NUMBERS over adjectives. Use specific data points, percentages, ratios, and metrics.
    - AVOID vague descriptors like "鏄捐憲", "澶у箙", "鏄庢樉", "寮哄姴". Replace with exact figures.
    - When management uses qualitative language (e.g., "strong growth"), convert to quantitative data if available (e.g., "revenue +15% YoY").
    - Examples:
      鉂?"钀ユ敹澶у箙澧為暱" 鈫?鉁?"钀ユ敹澧為暱15% YoY鑷?5.2B"
      鉂?"鍒╂鼎鐜囨樉钁椾笅婊? 鈫?鉁?"钀ヤ笟鍒╂鼎鐜囦粠18.5%闄嶈嚦14.2%"
      鉂?"瀹㈡祦鏄庢樉鍥炲崌" 鈫?鉁?"浜ゆ槗閲忓闀?.2% QoQ"
    - If specific numbers are not available, state "鏁版嵁鏈姭闇? instead of using vague language.

    **Report Structure (in Chinese)**:
    # {data['name']} ({data['symbol']}) - Company Update

    ## 1. Executive Summary (鏍稿績鎽樿)
    [Brief overview with key metrics. Highlight any BREAKING NEWS if present]
    - **Valuation**: Forward PE: {data['forward_pe']} | Trailing PE: {data['pe']}

    ## 2. Breaking News & Events (绐佸彂/浠婃棩浜嬩欢)
    [Detail specific breaking news with dates and numbers. If none, skip.]

    ## 3. Recent Earnings Details (鏈€鏂拌储鎶ヨ鎯?- Within 1 Week)
    **CRITICAL**: IF earnings were released within the last 7 days, provide a detailed breakdown here.
    - **Revenue**: Actual vs Estimate (Specify the exact numbers)
    - **EPS**: Actual vs Estimate (Specify the exact numbers)
    - **Key Metrics**: (e.g., Margins, User Growth, Same-Store Sales) - Use a table or bullet points with EXACT numbers.
    - **YoY/QoQ Changes**: Explicitly state the percentage changes.

    ## 4. Management Guidance (绠＄悊灞傛寚寮?- Numeric Focus)
    **CRITICAL**: You MUST extract specific numbers for future guidance. Do not just say "raised guidance".
    - **Next Quarter Outlook**: Revenue range ($X - $Y), EPS range ($A - $B).
    - **Full Year Outlook**: Revenue range ($X - $Y), EPS range ($A - $B).
    - **Key Assumptions**: (e.g., "Operating margin expansion of 50bps").
    *If numeric guidance is not explicitly found in the snippets, state "Specific numeric guidance not found in available sources" but attempt to infer from descriptions like "mid-single digit growth".*

    ## 5. Investment Verdict (鎶曡祫缁撹)
    [Bullish/Bearish/Neutral with quantitative support]
    """

    response = GEMINI_CLIENT.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    text = _extract_response_text(response)
    # Clean up markdown code blocks if present
    if text.strip().startswith("```"):
        lines = text.strip().split("\n")
        # Remove start fence
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove end fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_company.py [TICKER]")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    data = fetch_data(ticker)

    if data:
        # Load KB context and holdings status BEFORE searching
        print("馃摎 Loading knowledge base context...")
        kb_ctx       = load_kb_context(ticker)
        holdings_ctx = load_holdings_context(ticker)
        if kb_ctx:
            print(f"  鉁?KB hit for {ticker} 鈥?incremental update mode")
        else:
            print(f"  鈩癸笍  No KB entry for {ticker} 鈥?first analysis")

        # 1. Broad News (Past Week)
        news = fetch_news(f"{ticker} stock analysis latest trends", freshness="pw")

        # 2. Earnings/Guidance (Past Month)
        earnings = fetch_news(f"{ticker} earnings call transcript guidance outlook", freshness="pm")

        # 3. BREAKING NEWS (Today/Past Day)
        breaking = fetch_news(f"{ticker} management presentation conference call CEO today", freshness="pd")

        report = generate_report(data, news, earnings, breaking,
                                 kb_ctx=kb_ctx, holdings_ctx=holdings_ctx)

        # Save Report
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{timestamp}_{ticker}_Update.md" # Changed to match existing format: YYYYMMDD_TICKER_Update.md

        # Create date-based subdirectory
        reports_dir = os.path.join(project_root, "Reports", timestamp)
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)

        filepath = os.path.join(reports_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
            f.write(f"\n\n---\n*Generated by /update on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        print(f"鉁?Report saved: {filepath}")

        # Sync to Obsidian
        try:
            import sync_to_obsidian
            sync_to_obsidian.sync_reports()
            print("鉁?Synced to Obsidian.")
        except Exception as e:
            print(f"鈿狅笍 Obsidian Sync Failed: {e}")
            # Try explicit path import if failed
            try:
                sys.path.append(script_dir)
                import sync_to_obsidian
                sync_to_obsidian.sync_reports()
            except:
                pass
