import logging
import praw
import time
import random
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CommunityScraper:
    def __init__(self, config):
        self.config = config
        self.reddit = None
        self._init_reddit()

    def _get_keywords(self, watchlist):
        """Extract all stock symbols and names for filtering."""
        keywords = set()
        for market in watchlist.values():
            for stock in market:
                keywords.add(stock['symbol'].lower())
                keywords.add(stock['name'].lower())
                # Add simple variants? e.g. NVDA -> nvidia
                pass
        return keywords

    def _init_reddit(self):
        """Initialize Reddit API client."""
        r_conf = self.config.get('reddit', {})
        client_id = r_conf.get('client_id')
        client_secret = r_conf.get('client_secret')
        user_agent = r_conf.get('user_agent', 'invest_bot_v1')

        # Only init PRAW if keys specificly provided clearly
        if client_id and client_secret and "YOUR" not in client_id:
            try:
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent
                )
                logger.info("Reddit Client Initialized (API Mode).")
            except Exception as e:
                logger.error(f"Failed to init Reddit: {e}")
        else:
            logger.info("Reddit API keys not found. Will use RSS fallback.")

    def fetch_reddit_posts(self, subreddits=['wallstreetbets', 'investing', 'stocks'], limit=10, watchlist=None):
        """
        Fetch hot/new posts from subreddits.
        """
        all_posts = []
        keywords = self._get_keywords(watchlist) if watchlist else set()

        # Mode A: API (PRAW)
        if self.reddit:
            for sub_name in subreddits:
                try:
                    subreddit = self.reddit.subreddit(sub_name)
                    # Respect limit per subreddit, or limit total? 
                    # Request says "max 10 from each channel". 
                    # So 10 from Reddit total or per sub? Usually per channel implies Source.
                    # Let's distribute limit across subs or just simple limit.
                    # Assuming limit is TOTAL for this scraper to adhere to "per channel max 10"
                    
                    fetch_count = limit // len(subreddits) + 1 # Simple distribution
                    
                    for submission in subreddit.hot(limit=fetch_count + 5): # Fetch a bit more to filter
                        if len(all_posts) >= limit: break
                        if submission.stickied: continue
                        if submission.score < 50: continue

                        # Keyword Filter
                        if keywords:
                            text_to_search = (submission.title + " " + submission.selftext).lower()
                            if not any(k in text_to_search for k in keywords):
                                continue

                        all_posts.append({
                            'title': f"[Reddit/{sub_name}] {submission.title}",
                            'link': submission.url,
                            'published': datetime.fromtimestamp(submission.created_utc).isoformat(),
                            'source': f"Reddit r/{sub_name}",
                            'summary': submission.selftext[:500] + "...",
                            'lang': 'en',
                            'score_raw': submission.score,
                            'type': 'community'
                        })
                except Exception as e:
                    logger.error(f"Error fetching Reddit API r/{sub_name}: {e}")

        # Mode B: RSS (No credentials needed)
        else:
            for sub_name in subreddits:
                try:
                    rss_url = f"https://www.reddit.com/r/{sub_name}/hot.rss"
                    feed = feedparser.parse(rss_url)
                    
                    count = 0
                    for entry in feed.entries:
                        if count >= limit: break
                        
                        # RSS summary is often HTML, might need cleanup but raw is ok for LLM
                        # RSS doesn't give score easily, assuming 'hot' implies some value.
                        
                        # Keyword Filter
                        if keywords:
                            text_to_search = (entry.title + " " + entry.summary).lower()
                            if not any(k in text_to_search for k in keywords):
                                continue

                        all_posts.append({
                            'title': f"[Reddit/{sub_name}] {entry.title}",
                            'link': entry.link,
                            'published': datetime(*entry.published_parsed[:6]).isoformat(),
                            'source': f"Reddit r/{sub_name}",
                            'summary': entry.summary[:500] + "...", # Contains HTML usually
                            'lang': 'en',
                            'type': 'community'
                        })
                        count += 1
                        
                except Exception as e:
                    logger.error(f"Error fetching Reddit RSS r/{sub_name}: {e}")
        
        return all_posts

    def run(self, watchlist, limit=10):
        """
        Main execution for community.
        """
        all_items = []
        
        # 1. Reddit Channel
        # Default subreddits to monitor
        subs = ['wallstreetbets', 'investing', 'stocks', 'China_irl']
        
        # Optimization: Filter by keywords to avoid noise
        # fetch_reddit_posts needs to know about keywords now? 
        # Or we simply fetch and filter here. 
        # Ideally pass keywords to fetch method.
        # Let's update fetch_reddit_posts signature or filter inside if simple.
        
        # Passing watchlist to fetch_reddit_posts is cleaner
        all_items.extend(self.fetch_reddit_posts(subreddits=subs, limit=limit, watchlist=watchlist))
        
        # 2. Xueqiu Channel (Future)
        # xueqiu_items = self.fetch_xueqiu(limit=limit)
        # all_items.extend(xueqiu_items)
        
        # 3. EastMoney Guba Channel
        try:
           guba_items = self.fetch_guba_posts(watchlist, limit=limit)
           all_items.extend(guba_items)
        except Exception as e:
           logger.error(f"Guba scraping failed: {e}")
        
        return all_items

    def fetch_guba_posts(self, watchlist, limit=10):
        """
        Fetch posts from EastMoney Guba for CN stocks.
        """
        all_posts = []
        stocks = watchlist.get('cn', [])
        if not stocks:
            return []
            
        # Distribute limit across stocks to avoid one stock filling all 10 slots
        # If we have 3 stocks, limit is 10. 3 per stock approx.
        per_stock_limit = max(1, limit // len(stocks))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        for stock in stocks:
            if len(all_posts) >= limit: break
            
            symbol = stock['symbol']
            # Guba uses 6 digit code. 600519 -> 600519
            # Verify symbol format if needed
            
            url = f"https://guba.eastmoney.com/list,{symbol}.html"
            try:
                response = requests.get(url, headers=headers, timeout=5)
                # Parse
                if response.status_code == 200:
                    # Simple regex or split might be safer if BS4 fails on some partial HTML
                    # But let's try BS4 first
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'lxml')
                    
                    # Strategy: Try to find 'tr.listitem' which seems to be the current structure
                    # Also keep 'div.articleh' as fallback if needed
                    
                    posts = []
                    
                    # 1. Try finding tr.listitem (Common in 2022+ Guba)
                    # Use a broad select to find them anywhere inside mainlist
                    posts = soup.select("#mainlist .listitem")
                    
                    # 2. If empty, try old div.articleh
                    if not posts:
                         posts = soup.find_all('div', class_='articleh')

                    count = 0
                    for post in posts:
                        if count >= per_stock_limit: break
                        if len(all_posts) >= limit: break
                        
                        try:
                            # Skip ads (often have class ad_post)
                            if 'ad_post' in post.get('class', []): continue
                            
                            # TITLE & LINK
                            # Try .title > a (New) or span.l3 > a (Old)
                            title_tag = None
                            title_div = post.find('div', class_='title')
                            
                            if title_div:
                                title_tag = title_div.find('a')
                            else:
                                # Fallback to old span.l3
                                l3 = post.find('span', class_='l3')
                                if l3: title_tag = l3.find('a')
                                
                            if not title_tag: continue
                            
                            title = title_tag.get('title') or title_tag.text.strip()
                            href = title_tag.get('href')
                            
                            if not href: continue
                            
                            # Fix Link
                            if href.startswith('//'): full_link = f"https:{href}"
                            elif href.startswith('/'): full_link = f"https://guba.eastmoney.com{href}"
                            else: full_link = href
                            
                            # READ COUNT
                            # Try .read (New) or span.l1 (Old)
                            read_count = 0
                            read_div = post.find('div', class_='read')
                            if not read_div: read_div = post.find('span', class_='l1')
                            
                            if read_div:
                                txt = read_div.text.strip()
                                if txt.isdigit(): read_count = int(txt)
                                elif '万' in txt: 
                                    try: read_count = int(float(txt.replace('万','')) * 10000)
                                    except: pass
                            
                            if read_count < 100: continue
                            
                            all_posts.append({
                                'title': f"[Guba/{stock['name']}] {title}",
                                'link': full_link,
                                'published': datetime.now().isoformat(), 
                                'source': 'EastMoney Guba',
                                'summary': title,
                                'lang': 'zh-CN',
                                'type': 'community'
                            })
                            count += 1
                        except Exception as ex:
                            # logger.debug(f"Skipping post: {ex}")
                            continue
                            
            except Exception as e:
                logger.error(f"Error scraping Guba for {symbol}: {e}")
                
        return all_posts
