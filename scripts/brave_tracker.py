"""
Brave Search API 使用统计追踪器
用于监控免费版 API 配额消耗（每月 2000 次）
"""

import os
import json
from datetime import datetime
from pathlib import Path

class BraveAPITracker:
    """Track Brave Search API usage to monitor quota."""
    
    def __init__(self, log_file=None):
        """
        Initialize tracker.
        
        Args:
            log_file: Path to usage log file (default: tools/brave_usage.json)
        """
        if log_file is None:
            script_dir = Path(__file__).parent
            log_file = script_dir / "brave_usage.json"
        
        self.log_file = Path(log_file)
        self.usage_data = self._load_usage()
    
    def _load_usage(self):
        """Load existing usage data."""
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            "total_calls": 0,
            "monthly_calls": {},
            "last_reset": datetime.now().strftime("%Y-%m-01"),
            "calls_by_type": {
                "stock_news": 0,
                "market_movers": 0,
                "sector_news": 0,
                "macro_event": 0
            }
        }
    
    def _save_usage(self):
        """Save usage data to file."""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.usage_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save usage log: {e}")
    
    def _get_current_month(self):
        """Get current month key (YYYY-MM)."""
        return datetime.now().strftime("%Y-%m")
    
    def record_call(self, call_type="stock_news"):
        """
        Record an API call.
        
        Args:
            call_type: Type of search (stock_news, market_movers, sector_news, macro_event)
        """
        current_month = self._get_current_month()
        
        # Initialize month if needed
        if current_month not in self.usage_data["monthly_calls"]:
            self.usage_data["monthly_calls"][current_month] = 0
        
        # Increment counters
        self.usage_data["total_calls"] += 1
        self.usage_data["monthly_calls"][current_month] += 1
        
        if call_type in self.usage_data["calls_by_type"]:
            self.usage_data["calls_by_type"][call_type] += 1
        
        self._save_usage()
    
    def get_monthly_usage(self):
        """Get current month's usage."""
        current_month = self._get_current_month()
        return self.usage_data["monthly_calls"].get(current_month, 0)
    
    def get_remaining_quota(self, monthly_limit=2000):
        """
        Get remaining API calls for current month.
        
        Args:
            monthly_limit: Monthly quota limit (default: 2000 for free tier)
            
        Returns:
            Remaining calls
        """
        used = self.get_monthly_usage()
        return max(0, monthly_limit - used)
    
    def should_use_api(self, monthly_limit=2000, reserve=100):
        """
        Check if API should be used based on quota.
        
        Args:
            monthly_limit: Monthly quota limit
            reserve: Reserve quota to keep (don't use last N calls)
            
        Returns:
            True if safe to use API, False if quota is low
        """
        remaining = self.get_remaining_quota(monthly_limit)
        return remaining > reserve
    
    def get_stats(self):
        """Get usage statistics."""
        current_month = self._get_current_month()
        monthly_used = self.get_monthly_usage()
        
        return {
            "total_calls": self.usage_data["total_calls"],
            "current_month": current_month,
            "monthly_used": monthly_used,
            "monthly_remaining": max(0, 2000 - monthly_used),
            "calls_by_type": self.usage_data["calls_by_type"]
        }
    
    def print_stats(self):
        """Print usage statistics to console."""
        stats = self.get_stats()
        
        print("\n" + "="*50)
        print("📊 Brave Search API 使用统计")
        print("="*50)
        print(f"当前月份: {stats['current_month']}")
        print(f"本月已用: {stats['monthly_used']} / 2000")
        print(f"剩余配额: {stats['monthly_remaining']}")
        print(f"\n累计调用: {stats['total_calls']}")
        print("\n调用类型分布:")
        for call_type, count in stats['calls_by_type'].items():
            print(f"  - {call_type}: {count}")
        print("="*50 + "\n")


# Global tracker instance
_tracker = None

def get_tracker():
    """Get global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = BraveAPITracker()
    return _tracker


if __name__ == "__main__":
    # Test tracker
    tracker = BraveAPITracker()
    
    # Simulate some calls
    tracker.record_call("stock_news")
    tracker.record_call("stock_news")
    tracker.record_call("sector_news")
    
    # Print stats
    tracker.print_stats()
