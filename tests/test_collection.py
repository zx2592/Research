import logging
import yaml
import json
import os
import sys

# Ensure we can import from local directories
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers.news_scraper import NewsScraper
from scrapers.market_data import MarketDataFetcher
from scrapers.report_scraper import ReportScraper
from scrapers.community import CommunityScraper

# Setup logging to both console and system.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TEST - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("system.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TestCollector")

def load_config():
    with open('d:/AI/Auto/system/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run_test():
    logger.info("Starting Single Stock Collection Test for: Apple (AAPL)")
    
    config = load_config()
    
    # Construct a specific test watchlist for Apple
    test_watchlist = {
        "cn": [],
        "us": [{"symbol": "AAPL", "name": "Apple"}],
        "hk": [],
        "jp": [],
        "keywords": [] 
    }

    # Initialize Scrapers
    logger.info("Initializing scrapers...")
    news_scraper = NewsScraper(config['scraping'])
    market_fetcher = MarketDataFetcher(config)
    report_scraper = ReportScraper(config)
    community_scraper = CommunityScraper(config)

    # 1. News
    logger.info(">>> Testing News Scraper (US/Global)...")
    news_items = news_scraper.run(test_watchlist)
    for item in news_items:
        logger.info(f"[NEWS] Found: {item['title']} ({item['source']})")
    if not news_items:
        logger.info("[NEWS] No recent news found.")

    # 2. Market Data
    logger.info(">>> Testing Market Data (US)...")
    price_data = market_fetcher.get_price_snapshot("AAPL", market="us")
    if price_data:
        logger.info(f"[MARKET] Price: ${price_data['price']:.2f}, Change: {price_data['pct_change']:.2f}%")
    else:
        logger.error("[MARKET] Failed to fetch price data.")

    # 3. Reports
    logger.info(">>> Testing Report Scraper (SEC)...")
    reports = report_scraper.run(test_watchlist)
    for item in reports:
        logger.info(f"[REPORT] Found: {item['title']}")
    if not reports:
        logger.info("[REPORT] No recent SEC reports found.")

    # 4. Community
    logger.info(">>> Testing Community Scraper (Reddit)...")
    # Fetch general posts
    community_items = community_scraper.run(test_watchlist)
    # Filter for Apple related
    related_items = [i for i in community_items if "Apple" in i['title'] or "AAPL" in i['title'] or "iPhone" in i['title']]
    
    if related_items:
        for item in related_items:
            logger.info(f"[COMMUNITY] Found: {item['title']}")
    else:
        logger.info(f"[COMMUNITY] No specific Apple/AAPL posts found in hot threads (Total generic fetched: {len(community_items)}).")

    logger.info("Apple Test Complete. Check system.log for details.")

if __name__ == "__main__":
    run_test()
