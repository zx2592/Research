#!/usr/bin/env python3
"""
Utility: Write report content from a temp file to the target path.
Usage: python scripts/_write_report.py <target_path> <content_file>

This exists to work around IDE write_to_file tool timeouts on large markdown.
"""
import sys
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: python _write_report.py <target_path> <content_file>")
        sys.exit(1)
    
    target = sys.argv[1]
    content_file = sys.argv[2]
    
    with open(content_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"OK: {target} ({len(content)} bytes)")

if __name__ == "__main__":
    main()
