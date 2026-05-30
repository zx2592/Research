import sqlite3
import logging
from datetime import datetime
import hashlib
import difflib

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.db_path = config['system']['database_path']
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Table for processed items to avoid duplicates
        c.execute('''
            CREATE TABLE IF NOT EXISTS processed_items (
                id TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                publish_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for logs/history
        c.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                score INTEGER,
                summary TEXT,
                reasoning TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()

    def _generate_id(self, item):
        """Generate a stable ID based on Title + Source."""
        title = item.get('title', '').strip()
        source = item.get('source', '').strip()
        # Fallback if empty
        if not title: 
            return item.get('link') 
            
        unique_str = f"{title}_{source}"
        return hashlib.md5(unique_str.encode('utf-8')).hexdigest()

    def is_new(self, item):
        """
        Check if item is new based on ID.
        """
        item_id = self._generate_id(item)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT 1 FROM processed_items WHERE id = ?', (item_id,))
        exists = c.fetchone()
        conn.close()
        
        return not exists

    def mark_processed(self, item):
        """
        Mark item as processed.
        """
        item_id = self._generate_id(item)
        title = item.get('title')
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO processed_items (id, title, source, publish_date) VALUES (?, ?, ?, ?)',
                      (item_id, title, item.get('source'), item.get('published')))
            conn.commit()
        except Exception as e:
            logger.error(f"Error marking item processed: {e}")
        finally:
            conn.close()

    def save_result(self, item):
        """
        Save analyzed result to history.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO history (title, score, summary, reasoning, url)
                VALUES (?, ?, ?, ?, ?)
            ''', (item.get('title'), item.get('score'), item.get('summary'), 
                  item.get('reasoning'), item.get('link')))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving result: {e}")
        finally:
            conn.close()

    def filter_new_items(self, items):
        """
        Filter out items that have already been processed (Exact deduplication).
        """
        new_items = []
        for item in items:
            if self.is_new(item):
                new_items.append(item)
        return new_items

    def semantic_deduplication(self, items, similarity_threshold=0.75):
        """
        Deduplicate items based on title similarity.
        Keep the one with higher priority source or longer summary.
        Priority: Report (SEC) > Market > News > Community
        """
        if not items:
            return []

        # Sort items by source priority just to have a deterministic order
        # We can map source types to weight
        def get_source_weight(item):
            src = item.get('source', '').lower()
            if 'sec' in src or 'filing' in src: return 4
            if 'alert' in src or 'market' in src: return 3
            if 'news' in src: return 2
            if 'reddit' in src or 'community' in src: return 1
            return 0

        # Sort by weight desc, then date desc
        items.sort(key=lambda x: (get_source_weight(x), x.get('published', '')), reverse=True)

        unique_items = []
        
        for item in items:
            is_dup = False
            title1 = item.get('title', '')
            
            for index, existing_item in enumerate(unique_items):
                title2 = existing_item.get('title', '')
                
                # Check similarity
                ratio = difflib.SequenceMatcher(None, title1, title2).ratio()
                if ratio > similarity_threshold:
                    is_dup = True
                    # Optional: Merge info? e.g. if one has full text and other doesn't?
                    # For now just drop the lower priority one (start of loop item)
                    # Because we sorted by priority, 'existing_item' is higher or equal priority.
                    break
            
            if not is_dup:
                unique_items.append(item)
                
        return unique_items

    def cap_items(self, items, limit=10):
        """
        Limit the number of items, prioritizing diversity or just top N.
        Assumes items are already sorted/deduplicated.
        """
        return items[:limit]
