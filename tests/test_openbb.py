import logging
import sys
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestOpenBB")

try:
    logger.info("Importing OpenBB...")
    from openbb import obb
    logger.info("OpenBB imported successfully.")
    
    logger.info("Testing World News fetch...")
    # Using 'yfinance' or default provider if available
    # Note: 'openbb' v4 requires 'openbb-news' or similar extensions sometimes?
    # Standard 'openbb' package should include core.
    
    # Try fetching world news
    try:
        news = obb.news.world(limit=5)
        logger.info(f"Fetched {len(news.results) if hasattr(news, 'results') else 'some'} world news items.")
        print(news)
    except Exception as e:
        logger.warning(f"World news fetch failed (might need provider setup): {e}")

    logger.info("Test Complete.")
    
except ImportError:
    logger.error("OpenBB not installed. Run 'pip install openbb'.")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
