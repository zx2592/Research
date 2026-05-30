import os, shutil

src_dir = os.path.join(os.path.dirname(__file__), "Skills", "references")

renames = {
    "p1-genesis.md": "deep-genesis.md",
    "p2-phase-check.md": "deep-phase-check.md",
    "p3-event-impact.md": "quick-event-impact.md",
    "p4-radar.md": "radar-checklist.md",
    "p5-fomo-killer.md": "buy-fomo-killer.md",
    "p6-profit-keeper.md": "sell-profit-keeper.md",
    "p7-portfolio-check.md": "position-portfolio.md",
    "p8-macro-filter.md": "macro-filter.md",
    "p9-valuation.md": "deep-valuation.md",
    "p10-options.md": "option-strategy.md",
    "p11-autopsy.md": "rethink-autopsy.md",
    "p12-referee.md": "buy-sell-referee.md",
    "p13-market-scanner.md": "scan-market-scanner.md",
    "p14-sector-hunter.md": "scan-sector-hunter.md",
    "p15-insight.md": "quick-insight.md",
}

for old, new in renames.items():
    old_path = os.path.join(src_dir, old)
    new_path = os.path.join(src_dir, new)
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        print(f"  {old} -> {new}")
    else:
        print(f"  SKIP: {old}")

print(f"\nDone! Files: {sorted(os.listdir(src_dir))}")
