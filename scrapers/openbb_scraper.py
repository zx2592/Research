import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

class OpenBBScraper:
    def __init__(self, config):
        self.config = config
        self.obb = None
        self._init_openbb()

    def _init_openbb(self):
        """Initialize OpenBB Platform."""
        try:
            from openbb import obb
            self.obb = obb
            logger.info("OpenBB Platform Initialized.")
        except ImportError:
            logger.error("OpenBB package not found. Please install `openbb`.")
        except Exception as e:
            logger.error(f"Failed to init OpenBB: {e}")

    def fetch_company_news(self, symbol, limit=10):
        """
        Fetch company specific news.
        """
        if not self.obb: return []
        
        items = []
        try:
            # openbb v4 usage: obb.news.company(symbol="AAPL", provider="yfinance")
            # We explicitly use yfinance as it is free and reliable usually
            # Tiingo/Benzinga need keys
            
            # Note: returns OBBObject, usually with .results or to_dataframe()
            # Let's try to get a few more to filter
            # Date filtering might be needed
            
            # Since standard yfinance fetcher handles price, here we focus on News text
            
            # Providers: yfinance, polygon, benzinga, tiingo...
            # We try default first (which might be yfinance)
            news_df = self.obb.news.company(symbol=symbol, limit=limit, provider='yfinance').to_df()
            
            if not news_df.empty:
                for _, row in news_df.iterrows():
                    # Columns often: date, title, content, link, etc.
                    # Adjust based on actual OpenBB output columns
                    
                    title = row.get('title')
                    if not title: continue
                    
                    link = row.get('url') or row.get('link')
                    published = row.get('date')
                    if not isinstance(published, str):
                        published = str(published)
                        
                    items.append({
                        'title': f"[OpenBB/{symbol}] {title}",
                        'link': link,
                        'published': published,
                        'source': 'OpenBB/yfinance',
                        'summary': row.get('text') or row.get('summary') or title,
                        'lang': 'en',
                        'type': 'news'
                    })
                    
        except Exception as e:
            # logger.error(f"OpenBB fetch failed for {symbol}: {e}")
            pass
            
        return items

    def fetch_world_news(self, limit=10):
        """
        Fetch global market news.
        """
        if not self.obb: return []
        
        items = []
        try:
            # obb.news.world(limit=limit)
            results = self.obb.news.world(limit=limit).to_df()
            
            if not results.empty:
                for _, row in results.iterrows():
                    items.append({
                        'title': f"[OpenBB/World] {row.get('title')}",
                        'link': row.get('url') or row.get('link'),
                        'published': str(row.get('date')),
                        'source': 'OpenBB/World',
                        'summary': row.get('text') or row.get('summary') or row.get('title'),
                        'lang': 'en',
                        'type': 'news'
                    })
        except Exception as e:
            logger.error(f"OpenBB world news fetch failed: {e}")
            
        return items

    def run(self, watchlist, limit=10):
        """
        Main execution for OpenBB.
        """
        all_items = []
        
        # 1. World News (Global Limit)
        # User Feedback: "Irrelevant international news". 
        # Disable generic world news for company-specific monitoring.
        # world_limit = max(2, limit // 5) 
        # all_items.extend(self.fetch_world_news(limit=world_limit))
        
        # 2. Company News (US Stocks primarily)
        # Allocate full limit to companies
        us_stocks = watchlist.get('us', [])
        if us_stocks:
            per_stock = max(1, limit // len(us_stocks))
            for stock in us_stocks:
                if len(all_items) >= limit: break
                
                news = self.fetch_company_news(stock['symbol'], limit=per_stock)
                all_items.extend(news)
                
        return all_items[:limit]
