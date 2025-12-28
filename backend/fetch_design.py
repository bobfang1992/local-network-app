#!/usr/bin/env python3
"""Fetch and analyze usgraphics.com design"""

import urllib.request
import re
from html.parser import HTMLParser

class StyleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.styles = []
        self.in_style = False
        self.body_classes = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'style':
            self.in_style = True
        elif tag == 'body':
            if 'class' in attrs_dict:
                self.body_classes = attrs_dict['class'].split()

    def handle_data(self, data):
        if self.in_style:
            self.styles.append(data)

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False

url = 'https://usgraphics.com/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

try:
    print(f"Fetching {url}...")
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=10) as response:
        html = response.read().decode('utf-8')

    print(f"✓ Fetched {len(html)} bytes")
    print("\n" + "="*60)
    print("ANALYZING DESIGN ELEMENTS")
    print("="*60)

    # Parse styles
    parser = StyleParser()
    parser.feed(html)

    # Extract key design elements
    print("\n1. CSS STYLES FOUND:")
    print("-" * 60)
    for i, style in enumerate(parser.styles[:3], 1):  # First 3 style blocks
        print(f"\nStyle block {i}:")
        print(style[:500])  # First 500 chars
        if len(style) > 500:
            print("... (truncated)")

    # Extract font families
    print("\n\n2. FONT FAMILIES:")
    print("-" * 60)
    fonts = re.findall(r'font-family:\s*([^;]+);', html)
    for font in set(fonts[:5]):
        print(f"  - {font}")

    # Extract color scheme
    print("\n\n3. COLOR PALETTE:")
    print("-" * 60)
    colors = re.findall(r'(?:color|background-color|border-color):\s*(#[0-9a-fA-F]{3,6}|rgb[a]?\([^)]+\)|[a-z]+);', html)
    unique_colors = list(set(colors[:20]))
    for color in unique_colors:
        print(f"  - {color}")

    # Extract font sizes
    print("\n\n4. FONT SIZES:")
    print("-" * 60)
    sizes = re.findall(r'font-size:\s*([^;]+);', html)
    unique_sizes = list(set(sizes[:15]))
    for size in unique_sizes:
        print(f"  - {size}")

    # Extract spacing
    print("\n\n5. SPACING/PADDING:")
    print("-" * 60)
    spacing = re.findall(r'(?:margin|padding):\s*([^;]+);', html)
    unique_spacing = list(set(spacing[:15]))
    for space in unique_spacing:
        print(f"  - {space}")

    # Extract body/main content structure
    print("\n\n6. PAGE STRUCTURE:")
    print("-" * 60)

    # Find main content area
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
    if main_match:
        print("✓ Has <main> tag")

    # Check for common layout patterns
    if 'container' in html.lower():
        print("✓ Uses container pattern")
    if 'grid' in html.lower():
        print("✓ Uses grid layout")
    if 'flex' in html.lower():
        print("✓ Uses flexbox")

    # Save full HTML for reference
    with open('/tmp/usgraphics.html', 'w') as f:
        f.write(html)
    print(f"\n✓ Full HTML saved to /tmp/usgraphics.html")

    # Extract and save just the CSS
    all_css = '\n\n'.join(parser.styles)
    with open('/tmp/usgraphics.css', 'w') as f:
        f.write(all_css)
    print(f"✓ CSS saved to /tmp/usgraphics.css")

    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)

except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
