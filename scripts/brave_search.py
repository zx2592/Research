"""
Brave Search API Utility Module
Provides market news and information retrieval for research workflows.
"""

import os
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from brave_tracker import get_tracker

# Load environment variables
load_dotenv()

class BraveSearchClient:
    """Client for Brave Search API with market research focus."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Brave Search client.
        
        Args:
            api_key: Brave Search API key (defaults to env variable)
        """
        self.api_key = api_key or os.getenv("BRAVE_SEARCH_API_KEY")
        if not self.api_key:
            raise ValueError("BRAVE_SEARCH_API_KEY not found in environment")
        
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key
        }
    
    def search(
        self, 
        query: str, 
        count: int = 10,
        freshness: Optional[str] = None,
        country: str = "CN"
    ) -> Dict:
        """
        Perform a web search.
        
        Args:
            query: Search query string
            count: Number of results (max 20)
            freshness: Time filter - 'pd' (past day), 'pw' (past week), 'pm' (past month), 'py' (past year)
            country: Country code for localized results (CN, US, HK, JP)
            
        Returns:
            Dict containing search results
        """
        params = {
            "q": query,
            "count": min(count, 20),
            "country": country
        }
        
        if freshness:
            params["freshness"] = freshness
        
        try:
            response = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Brave Search API Error: {e}")
            return {"error": str(e)}
    
    def search_stock_news(
        self, 
        ticker: str, 
        name: str,
        days: int = 1
    ) -> List[Dict[str, str]]:
        """
        Search for recent news about a specific stock.
        
        Args:
            ticker: Stock ticker symbol
            name: Company name (Chinese or English)
            days: How many days back to search (1, 7, 30)
            
        Returns:
            List of news items with title, description, url
        """
        # Map days to freshness parameter
        freshness_map = {1: "pd", 7: "pw", 30: "pm"}
        freshness = freshness_map.get(days, "pd")
        
        # Construct query
        query = f"{name} {ticker} 股票 新闻"
        
        # Track API usage
        tracker = get_tracker()
        tracker.record_call("stock_news")
        
        results = self.search(query, count=5, freshness=freshness)
        
        if "error" in results:
            return []
        
        news_items = []
        web_results = results.get("web", {}).get("results", [])
        
        for item in web_results:
            news_items.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", ""),
                "age": item.get("age", "")
            })
        
        return news_items
    
    def search_market_movers(
        self, 
        market: str = "A股",
        date: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Search for market top gainers/losers.
        
        Args:
            market: Market name (A股, 港股, 美股)
            date: Specific date (YYYY-MM-DD) or None for today
            
        Returns:
            List of search results about market movers
        """
        date_str = f"{date} " if date else "今日 "
        query = f"{date_str}{market} 涨跌幅榜 龙虎榜"
        
        # Track API usage
        tracker = get_tracker()
        tracker.record_call("market_movers")
        
        results = self.search(query, count=10, freshness="pd")
        
        if "error" in results:
            return []
        
        return results.get("web", {}).get("results", [])
    
    def search_sector_news(
        self, 
        sector: str,
        days: int = 1
    ) -> List[Dict[str, str]]:
        """
        Search for sector/industry news.
        
        Args:
            sector: Sector name (e.g., "半导体", "新能源车", "AI")
            days: How many days back to search
            
        Returns:
            List of news items
        """
        freshness_map = {1: "pd", 7: "pw", 30: "pm"}
        freshness = freshness_map.get(days, "pd")
        
        query = f"{sector} 行业 板块 异动 政策"
        
        # Track API usage
        tracker = get_tracker()
        tracker.record_call("sector_news")
        
        results = self.search(query, count=8, freshness=freshness)
        
        if "error" in results:
            return []
        
        news_items = []
        web_results = results.get("web", {}).get("results", [])
        
        for item in web_results:
            news_items.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", "")
            })
        
        return news_items
    
    def search_macro_event(
        self,
        event: str,
        days: int = 7
    ) -> List[Dict[str, str]]:
        """
        Search for macroeconomic events and policy news.
        
        Args:
            event: Event description (e.g., "美联储加息", "MIIT补贴政策")
            days: How many days back to search
            
        Returns:
            List of news items
        """
        freshness_map = {1: "pd", 7: "pw", 30: "pm"}
        freshness = freshness_map.get(days, "pw")
        
        # Track API usage
        tracker = get_tracker()
        tracker.record_call("macro_event")
        
        results = self.search(event, count=8, freshness=freshness)
        
        if "error" in results:
            return []
        
        news_items = []
        web_results = results.get("web", {}).get("results", [])
        
        for item in web_results:
            news_items.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", "")
            })
        
        return news_items


# Convenience functions for quick usage
def quick_stock_search(ticker: str, name: str) -> List[Dict]:
    """Quick search for stock news."""
    try:
        client = BraveSearchClient()
        return client.search_stock_news(ticker, name)
    except Exception as e:
        print(f"Search failed: {e}")
        return []


def quick_market_scan(market: str = "A股") -> List[Dict]:
    """Quick search for market movers."""
    try:
        client = BraveSearchClient()
        return client.search_market_movers(market)
    except Exception as e:
        print(f"Search failed: {e}")
        return []


if __name__ == "__main__":
    # Test the API
    print("🔍 Testing Brave Search API...\n")
    
    try:
        client = BraveSearchClient()
        
        # Test 1: Stock News
        print("Test 1: Stock News (示例)")
        news = client.search_stock_news("NVDA", "NVIDIA")
        for i, item in enumerate(news[:3], 1):
            print(f"  {i}. {item['title']}")
        
        print("\nTest 2: Market Movers (A股)")
        movers = client.search_market_movers("A股")
        for i, item in enumerate(movers[:3], 1):
            print(f"  {i}. {item.get('title', 'N/A')}")
        
        print("\nTest 3: Sector News (半导体)")
        sector = client.search_sector_news("半导体")
        for i, item in enumerate(sector[:3], 1):
            print(f"  {i}. {item['title']}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
