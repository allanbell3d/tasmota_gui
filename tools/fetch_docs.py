"""Fetch Tasmota Commands documentation from GitHub."""
import urllib.request
import json
import os
from datetime import datetime

URL = "https://raw.githubusercontent.com/tasmota/docs/master/docs/Commands.md"
OUTPUT_DIR = r"D:\IA\Claude\Tasmota_GUI\assets\reference\tasmota"
VERSION = "15.2.0"
DATE = "2026-01-05"

def fetch_and_save():
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Fetching from: {URL}")

    # Fetch the content
    with urllib.request.urlopen(URL) as response:
        content = response.read().decode('utf-8')

    print(f"Downloaded {len(content)} characters")

    # Save raw markdown
    md_path = os.path.join(OUTPUT_DIR, f"commands_raw_{DATE}_v{VERSION}.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Saved to: {md_path}")

    # Save metadata
    meta = {
        "fetch_date": DATE,
        "fetch_time": datetime.now().isoformat(),
        "source_url": URL,
        "tasmota_version": VERSION,
        "file_size_chars": len(content),
        "file_size_lines": content.count('\n')
    }

    meta_path = os.path.join(OUTPUT_DIR, f"fetch_info_{DATE}_v{VERSION}.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    print(f"Metadata saved to: {meta_path}")

    return content

if __name__ == "__main__":
    fetch_and_save()
