import os
import sys
import json
import datetime
from google import genai
from dotenv import load_dotenv
from kb_holdings import load_holdings_context

# Path Setup
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
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


def generate_market_scan_report(json_path, output_path):
    print(f"馃摉 Reading RSS data from {json_path}...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        sys.exit(1)

    # Get active market
    now = datetime.datetime.now()
    market_str = "A鑲?娓偂 (鐩樺墠/鐩樹腑)" if 9 <= now.hour < 16 else "缇庤偂/鍏ㄧ悆 (闅斿鏀剁洏)"

    # Extract titles and categories to feed to AI
    lines = []
    for item in data.get("data", []):
        cat_str = ",".join(item.get("categories", []))
        lines.append(f"[{item.get('source_name', 'Unknown')}] {item.get('title')} (Tags: {cat_str})")

    context_str = "\n".join(lines)

    # If context is too long, truncate it
    if len(context_str) > 50000:
        context_str = context_str[:50000] + "\n...[Truncated]"

    print("馃 Synthesizing report using Gemini...")

    # Load holdings context for portfolio-aware warnings
    holdings_ctx = load_holdings_context()  # None = full portfolio summary

    prompt = f"""
    Role: Senior Equity Research Analyst and Macro Strategist.
    Task: Write a "Market Scan Report" (甯傚満鍏ㄦ櫙鎵弿) based on the provided live RSS and News Intelligence.
    Target Audience: Professional Investors and Portfolio Managers.
    Language: Professional Simplified Chinese.

    Current Date: {now.strftime('%Y-%m-%d')}
    Current Main Market Focus: {market_str}

{holdings_ctx}
    **IMPORTANT**: Cross-reference the news with the portfolio above. In Section 4 (鎸佷粨棰勮), identify which holdings are directly impacted by today's signals.
    Bullish signals for held positions get 馃煝, bearish signals get 馃敶.

    **News & Intelligence Feed**:
    {context_str}

    **Instructions**:
    1. Analyze the news to find the core themes and market momentum (e.g. AI anxiety, AI hardware spending, Tariffs, Geopolitics, Resource stocks surging).
    2. Categorize the signals into Theme Convergence (涓婚鏀舵暃), High-Impact Anomaly (楂樺奖鍝嶅紓甯?, Cognitive Gap (璁ょ煡娓╁樊), and Deep Foundation (娣卞害鍩虹煶).
    3. Identify "Sector Hunters" (鏉垮潡鐚庢墜) - which sectors or stocks are the real leaders vs followers?
    4. Provide Momentum and Allocation thoughts.
    5. Follow this exact Markdown structure:

    # [YYYYMMDD] 甯傚満鍏ㄦ櫙鎵弿

    > **涓绘垬鍦猴細** {market_str}
    > **甯傚満浣撴俯锛?* [Risk On (杩涙敾) / Risk Off (闃插尽) / Chaos (娣锋矊)]
    > **涓€鍙ヨ瘽鎽樿锛?* [鏈€鏍稿績鐨勫啿绐佹垨涓荤嚎]

    ## 1. 甯傚満鏁版嵁閫熻

    ### 鎸囨暟涓庡ぇ绫昏祫浜?
    (If numerical data is missing from feeds, briefly mention the general trend like 'US Indices fell', 'Gold pulled back', 'Oil surged')
    | 璧勪骇 | 鏀剁洏/鐜颁环 | 娑ㄨ穼骞?| 澶囨敞 |
    | :--- | :--- | :--- | :--- |

    ### 鏉垮潡杞姩
    **娑ㄥ箙鍓嶄笁锛?*
    1. [鏉垮潡] +X.X% 鈥?[椹卞姩鍥犵礌]

    **璺屽箙鍓嶄笁锛?*
    1. [鏉垮潡] -X.X% 鈥?[椹卞姩鍥犵礌]

    ### 鍏抽敭涓偂寮傚姩
    | 鑲＄エ | 娑ㄨ穼骞?| 浜嬩欢/鍘熷洜 |
    | :--- | :--- | :--- |

    ## 2. 鎴樼暐淇″彿浠〃鐩?

    | 淇″彿绫诲瀷 | 鏍稿績涓婚 | 淇″彿瑙ｈ |
    | :--- | :--- | :--- |
    | 涓婚鏀舵暃 | ... | ... |
    | 楂樺奖鍝嶅紓甯?| ... | ... |
    | 璁ょ煡娓╁樊 | ... | ... |
    | 娣卞害鍩虹煶 | ... | ... |

    ## 3. 鏉垮潡鐚庢墜锛氬€欓€夋睜

    | 鏉垮潡/鏍囩殑 | 淇″彿绫诲瀷 | 瑙掕壊 | 閫昏緫 |
    | :--- | :--- | :--- | :--- |
    | ... | 涓婚鏀舵暃/寮傚父/... | 鐪熼緳澶?璺熼 | ... |

    > 璺ㄥ競鍦烘槧灏? [濡傛湁锛屾爣娉?A鑲♀啍缇庤偂鑱斿姩]

    ## 4. 鎸佷粨棰勮 (Portfolio Alerts)
    >鍩轰簬鎸佷粨鏁版嵁锛屼粖鏃ヤ俊鍙锋秹鍙婄殑鎸佷粨鏍囩殑鍙婂叾褰卞搷鏂瑰悜銆?
    | 鎸佷粨鏍囩殑 | 褰卞搷鏂瑰悜 | 瑙﹀彂浜嬩欢 |
    | :--- | :--- | :--- |
    | [涓偂] | 馃煝鍒╁ソ / 馃敶鍒╃┖ / 馃煛涓€?| [浜嬩欢绠€杩癩 |

    ## 5. 鍔胯兘涓庢満浼?

    ### 鐭湡鍔胯兘 (Momentum)
    - **[鏉垮潡/涓婚]**
      - 椹卞姩閫昏緫锛?..
      - 璧勯噾鎬佸害锛?..
      - 瑙傚療鐒︾偣锛?..

    ### 闀跨嚎閰嶇疆 (Allocation)
    - **[鏉垮潡/涓婚]**
      - 娣卞害閫昏緫锛?..

    ## 6. 椋庨櫓涓庣邯寰嬭鍛?
    - **[椋庨櫓鐐筣**: ...

    ---
    **鐢熸垚妯″瀷**: Gemini Flash Latest (Stable)
    """

    response = GEMINI_CLIENT.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    report_content = _extract_response_text(response)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"鉁?Report successfully generated at: {output_path}")


if __name__ == "__main__":
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")
    month_str = now.strftime("%Y-%m")
    json_path = os.path.join(project_root, f"Reports/Raw_Data/{month_str}/financial_data_{today_str}.json")
    output_path = os.path.join(project_root, f"Reports/{today_str}/{today_str}_Market_Scan.md")
    generate_market_scan_report(json_path, output_path)
