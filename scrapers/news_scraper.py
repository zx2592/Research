import feedparser
import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime, timedelta
import time
import random
from urllib.parse import quote

logger = logging.getLogger(__name__)

class NewsScraper:
    def __init__(self, config):
        self.config = config
        self.processed_ids = set() # Over time this should be loaded from DB
        
    def fetch_google_news(self, query, language='en'):
        """
        Fetch news from Google News RSS.
        """
        # Encode query
        encoded_query = quote(query)
        
        # Construct URL based on language/region
        if language == 'zh-CN':
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        elif language == 'ja':
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
        else: # Default US/English
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            
        logger.info(f"Fetching RSS: {rss_url}")
        
        try:
            feed = feedparser.parse(rss_url)
            articles = []
            
            for entry in feed.entries:
                # Basic dedup using link or title hash
                if entry.link in self.processed_ids:
                    continue
                    
                # Time filtering (e.g. last 24h)
                published_time = datetime(*entry.published_parsed[:6])
                if datetime.now() - published_time > timedelta(hours=self.config.get('news_history_hours', 24)):
                    continue
                
                article = {
                    'title': entry.title,
                    'link': entry.link,
                    'published': published_time.isoformat(),
                    'source': entry.source.title if hasattr(entry, 'source') else 'Google News',
                    'summary': entry.summary if hasattr(entry, 'summary') else '',
                    'lang': language
                }
                
                # Deeper scraping if needed (optional here to save time/bandwidth)
                # full_text = self.extract_full_text(article['link'])
                # article['content'] = full_text
                
                articles.append(article)
                self.processed_ids.add(entry.link)
                
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching Google News for {query}: {e}")
            return []

    def extract_full_text(self, url):
        """
        Simple extractor using requests and bs4.
        For production, use newspaper4k or similar for better extraction.
        """
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            # Google News links are redirects, requests handles them usually
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Very naive identifying of main text - paragraphs
            # This needs specific rules for specific sites for best results
            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text() for p in paragraphs])
            
            # Simple cleanup
            return text[:5000] # Limit to 5000 chars for LLM context window safety
        except Exception as e:
            logger.error(f"Error extracting text from {url}: {e}")
            return ""

    def run(self, watchlist):
        """
        Main execution method.
        """
        all_news = []
        
        # 1. Keywords search
        keywords = watchlist.get('keywords', [])
        for keyword in keywords:
            # Detect language roughly or search in multiple
            # Simple heuristic: if keyword has ascii only, search US, else CN?
            # Or just search both for all keywords? 
            # Let's search CN for Chinese chars, US for English
            
            is_ascii = all(ord(c) < 128 for c in keyword)
            lang = 'en' if is_ascii else 'zh-CN'
            
            news_items = self.fetch_google_news(keyword, language=lang)
            all_news.extend(news_items)
            time.sleep(random.uniform(1, 2)) # Respectful delay
            
        # 2. Company specific search
        # Merge all symbols
        for region, stocks in watchlist.items():
            if region == 'keywords': continue
            
            for stock in stocks:
                query = stock['name'] # Searching by name is often better for news than symbol
                lang = 'zh-CN' if region in ['cn', 'hk'] else 'en'
                if region == 'jp': lang = 'ja'
                
                news_items = self.fetch_google_news(query, language=lang)
                for item in news_items:
                    item['related_stock'] = stock['symbol']
                
                all_news.extend(news_items)
                time.sleep(random.uniform(1, 2))
                
        return all_news
