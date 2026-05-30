import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)

url = "https://guba.eastmoney.com/list,600519.html"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    
    soup = BeautifulSoup(resp.text, 'lxml')
    # Use the selector we found previously
    items = soup.select("#mainlist .table_list .tab_content li")
    
    if items:
        print(f"Found {len(items)} items.")
        print("First Item HTML structure:")
        print(items[0].prettify())
    else:
        print("No li items found in selectors.")
        # Fallback debug: print children of tab_content?
        tab = soup.select_one("#mainlist .table_list .tab_content")
        if tab:
            print("Tab content found, children:")
            for child in tab.children:
                if child.name:
                    print(f"Child: {child.name} Class: {child.get('class')}")
        
except Exception as e:
    print(f"Error: {e}")
