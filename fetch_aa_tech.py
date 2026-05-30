import urllib.request
import json
import logging
from datetime import datetime, timezone

_YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def get_aa_data():
    # 5 days of data to see trend and MA
    url = "https://query1.finance.yahoo.com/v8/finance/chart/AA?interval=1d&range=30d"
    try:
        req = urllib.request.Request(url, headers=_YAHOO_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        
        result = data["chart"]["result"][0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        
        quotes = result["indicators"]["quote"][0]
        closes = quotes["close"]
        
        # Filter out Nones
        closes = [c for c in closes if c is not None]
        
        ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        
        print(f"Price: {price}")
        print(f"MA10: {ma10}")
        print(f"MA20: {ma20}")
        print(f"Prev Close: {closes[-2] if len(closes) >= 2 else None}")
        print(f"Recent Closes: {closes[-5:]}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_aa_data()
