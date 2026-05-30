import sqlite3
import json
import os

db_path = 'data/portfolio/portfolio.db'
if not os.path.exists(db_path):
    print(f"DB not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT payload FROM portfolio_events")
rows = cur.fetchall()
aa_events = []
all_tickers = set()

for r in rows:
    data = json.loads(r[0])
    ticker = data.get('ticker')
    if ticker:
        all_tickers.add(ticker)
    if ticker == 'AA':
        aa_events.append(data)

print(f"All Tickers in Ledger: {list(all_tickers)}")
print(f"AA Events: {json.dumps(aa_events, indent=2)}")

# Also try to compute current shares for AA
shares = 0
for ev in aa_events:
    if ev.get('event_type') == 'fill':
        qty = float(ev.get('quantity', 0))
        side = ev.get('side')
        if side == 'buy':
            shares += qty
        elif side == 'sell':
            shares -= qty

print(f"Current AA Shares: {shares}")
conn.close()
