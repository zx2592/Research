import urllib.request
import xml.etree.ElementTree as ET

url = "http://216.225.205.215:1200/eastmoney/report/strategyreport"
print(f"Fetching {url}...")

try:
    with urllib.request.urlopen(url) as response:
        xml_content = response.read().decode("utf-8")
        print(f"Successfully fetched {len(xml_content)} bytes")
        
        try:
            root = ET.fromstring(xml_content)
            channel = root.find("channel")
            if channel is None:
                print("❌ No channel found")
            else:
                items = channel.findall("item")
                print(f"✅ Found {len(items)} items")
                if items:
                    print("First item title:", items[0].findtext("title"))
                    print("First item pubDate:", items[0].findtext("pubDate"))
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            print("First 500 chars of content:")
            print(xml_content[:500])

except Exception as e:
    print(f"❌ Fetch Error: {e}")
