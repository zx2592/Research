import logging
import yaml
import sys
import os
import json
import time

# Ensure we can import from local directories
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers.news_scraper import NewsScraper
from scrapers.market_data import MarketDataFetcher
from scrapers.report_scraper import ReportScraper
from scrapers.community import CommunityScraper
from core.processor import DataProcessor
from core.llm_analyzer import LLMAnalyzer
from notifiers.telegram_bot import TelegramNotifier
from notifiers.email_sender import EmailNotifier

# Optional OpenBB
try:
    from scrapers.openbb_scraper import OpenBBScraper
    OPENBB_AVAILABLE = True
except ImportError:
    OPENBB_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestFullFlow")

def load_config():
    with open('d:/AI/Auto/system/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run_test():
    logger.info("Starting Multi-Market Test (AVAV, Maiwei, Capcom)...")
    config = load_config()
    
    # 1. Setup Watchlist
    # AVAV (US), 迈为股份 (CN - 300751), Capcom (JP - 9697.T)
    watchlist = {
        "us": [
            {"symbol": "AVAV", "name": "AeroVironment"}
        ],
        "cn": [
            {"symbol": "300751", "name": "迈为股份"} # Guba needs raw code usually
        ],
        "hk": [],
        "jp": [
            {"symbol": "9697.T", "name": "Capcom"} 
        ]
    }
    
    # 2. Initialize Components
    logger.info("Initializing components...")
    news_scraper = NewsScraper(config['scraping'])
    community_scraper = CommunityScraper(config)
    
    # OpenBB might fail on 300751 without suffix, but generic news scraper works.
    if OPENBB_AVAILABLE:
        openbb_scraper = OpenBBScraper(config)
    
    processor = DataProcessor(config)
    llm = LLMAnalyzer(config)
    telegram_notifier = TelegramNotifier(config)
    email_notifier = EmailNotifier(config)
    
    # 3. Collect Data
    logger.info("Collecting data from all channels...")
    all_raw_items = []
    
    # News
    logger.info("- News (Google RSS)...")
    all_raw_items.extend(news_scraper.run(watchlist))
    
    # Community (Includes Guba for CN)
    logger.info("- Community (Reddit & Guba)...")
    try:
        all_raw_items.extend(community_scraper.run(watchlist, limit=10))
    except Exception as e:
        logger.error(f"Community scraping failed: {e}")

    # OpenBB
    if OPENBB_AVAILABLE:
        logger.info("- OpenBB...")
        try:
            all_raw_items.extend(openbb_scraper.run(watchlist, limit=10))
        except Exception as e:
            logger.error(f"OpenBB failed: {e}")
            
    logger.info(f"Total raw items: {len(all_raw_items)}")
    
    # 4. Processing
    logger.info("Processing & Deduplicating...")
    unique_items = processor.filter_new_items(all_raw_items)
    deduped_items = processor.semantic_deduplication(unique_items, similarity_threshold=0.75)
    logger.info(f"Unique items after dedup: {len(deduped_items)}")
    
    # 5. Limit for LLM
    final_items = processor.cap_items(deduped_items, limit=15)
    logger.info(f"Items to Analyze: {len(final_items)}")
    
    if not final_items:
        logger.warning("No new items to analyze.")
        return

    # 6. LLM Scoring (Concise Prompt)
    logger.info("Analyzing with Gemini (Concise Value Investing Prompt)...")
    analyzed_projects = llm.analyze_items(final_items)
    
    # 7. Notification Logic
    email_digest = []
    
    for item in analyzed_projects:
        score = item.get('score', 0)
        title = item.get('title')
        
        logger.info(f"Item: {title} | Score: {score}")
        
        # > 8 Telegram
        if score > 8:
            logger.info(">> High Priority! Sending Telegram.")
            telegram_notifier.send_sync(item)
            email_digest.append(item)
            
        # >= 3 Digest
        elif score >= 3:
            logger.info(">> Medium Priority. Adding to Digest.")
            email_digest.append(item)
            
        else:
            logger.info(">> Low/Irrelevant. Ignored.")
            
        # CRITICAL: Mark as processed to prevent duplicate alerts on re-runs
        processor.mark_processed(item)
            
    # Send Email Digest
    if email_digest:
        logger.info(f"Sending Digest Email with {len(email_digest)} items...")
        email_notifier.send_digest(email_digest)
            
    logger.info("Test Complete.")

if __name__ == "__main__":
    run_test()
