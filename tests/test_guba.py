import logging
import yaml
import sys
import os

# Ensure we can import from local directories
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers.community import CommunityScraper

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestGuba")

def load_config():
    with open('d:/AI/Auto/system/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run_test():
    logger.info("Starting Guba Scraper Test...")
    config = load_config()
    
    # Test watchlist with a known active stock (e.g. Moutai 600519)
    watchlist = {
        "cn": [{"symbol": "600519", "name": "贵州茅台"}],
        "us": [],
        "hk": [],
        "jp": []
    }

    scraper = CommunityScraper(config)
    
    # Test fetch_guba_posts directly
    logger.info("Fetching from Guba...")
    items = scraper.fetch_guba_posts(watchlist, limit=5)
    
    for item in items:
        logger.info(f"Found: {item['title']} - {item['link']}")
        
    if not items:
        logger.warning("No items found. Check network or selectors.")
    else:
        logger.info(f"Successfully fetched {len(items)} items.")

if __name__ == "__main__":
    run_test()
