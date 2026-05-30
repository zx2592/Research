import logging
import requests
from sec_edgar_downloader import Downloader
import feedparser
import akshare as ak
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)

class ReportScraper:
    def __init__(self, config):
        self.config = config
        self.download_dir = "d:/AI/Auto/system/downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        # Initialize SEC downloader
        self.sec_dl = Downloader("MyInvestmentBot", "myemail@example.com", self.download_dir)

    def fetch_sec_filings(self, symbol):
        """
        Fetch latest 8-K or 10-K/Q from SEC for US stocks.
        Note: The library downloads files. We need to check if new files arrived.
        For simplicity/speed in this bot, we might prefer RSS or just check index.
        However, sec-edgar-downloader is robust for actual content.
        
        Alternative: Use SEC RSS feed for real-time monitoring.
        https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=8-K&output=atom
        """
        reports = []
        try:
            # Using RSS for metadata is lighter than downloading full filings immediately
            rss_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=&output=atom"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries:
                if len(reports) >= 10: break # Hard limit per symbol internal
                # Filter for interesting forms: 8-K, 10-K, 10-Q
                if any(x in entry.category for x in ['8-K', '10-K', '10-Q']):
                     reports.append({
                        'title': f"SEC Filing {entry.category}: {entry.title}",
                        'link': entry.link,
                        'published': entry.updated, # ISO format usually
                        'source': 'SEC EDGAR',
                        'summary': f"New {entry.category} filing detected for {symbol}.",
                        'lang': 'en',
                        'type': 'report'
                    })
        except Exception as e:
            logger.error(f"Error checking SEC for {symbol}: {e}")
            
        return reports

    def fetch_juchao_reports(self, symbol):
        """
        Fetch announcements from Juchao for A-shares via Akshare.
        Symbol format for AKshare usually 6 digits.
        """
        reports = []
        try:
            # akshare.stock_zh_a_gdgs() is for shareholder updates
            # stock_notice_report is for announcements? 
            # Akshare API changes often. Let's try stock_notice_report or generic notice.
            # Using stock_zh_a_spot_em to ensure it's a valid stock first? No need.
            
            # Use 'stock_notice_report' if available, otherwise fallback.
            # A common one is stock_info_global_cls for news, but for REPORTS:
            # stock_announcement_cninfo(symbol="600519") seems plausible?
            # Actually akshare.stock_zh_a_hist doesn't give reports.
            
            # Let's try a direct request to generic news API often used in Akshare:
            # Or use EastMoney report interface which is stable.
            pass 
            # Placeholder: getting Juchao specific data via scraping is hard without stable API.
            # Eastmoney is easier.
            
        except Exception as e:
             logger.error(f"Error checking Juchao/Eastmoney for {symbol}: {e}")
        return reports
    
    def fetch_hkex_news(self, symbol):
        """
        Fetch HKEX news. 
        HKEX website is anti-scraping heavy. 
        Better to use generic financial news site covering HK stocks (like AAStocks or EastMoney HK).
        """
        return []

    def run(self, watchlist, limit=10):
        """
        Main execution for reports.
        """
        all_reports = []
        
        # 1. US Stocks (SEC Channel)
        sec_items = []
        for stock in watchlist.get('us', []):
            if len(sec_items) >= limit: break # Limit SEC specifically
            
            # Fetch
            items = self.fetch_sec_filings(stock['symbol'])
            
            # Add with space check
            remaining = limit - len(sec_items)
            sec_items.extend(items[:remaining])
            
        all_reports.extend(sec_items)
            
        # 2. CN Stocks (Juchao Channel) - Future placeholder
        # cn_items = []
        # for stock in watchlist.get('cn', []):
        #    if len(cn_items) >= limit: break
        #    ...
        # all_reports.extend(cn_items)
            
        return all_reports
