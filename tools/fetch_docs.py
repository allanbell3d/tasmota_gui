"""Fetch Tasmota Commands documentation from GitHub.

Usage:
    python tools/fetch_docs.py --version 15.2.0 [--date 2026-01-05]
"""
import argparse
import json
import urllib.request
from datetime import date, datetime
from pathlib import Path

URL = "https://raw.githubusercontent.com/tasmota/docs/master/docs/Commands.md"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "reference" / "tasmota"


def fetch_and_save(version: str, fetch_date: str) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching from: {URL}")

    with urllib.request.urlopen(URL) as response:
        content = response.read().decode('utf-8')

    print(f"Downloaded {len(content)} characters")

    md_path = OUTPUT_DIR / f"commands_raw_{fetch_date}_v{version}.md"
    md_path.write_text(content, encoding='utf-8')
    print(f"Saved to: {md_path}")

    meta = {
        "fetch_date": fetch_date,
        "fetch_time": datetime.now().isoformat(),
        "source_url": URL,
        "tasmota_version": version,
        "file_size_chars": len(content),
        "file_size_lines": content.count('\n')
    }

    meta_path = OUTPUT_DIR / f"fetch_info_{fetch_date}_v{version}.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(f"Metadata saved to: {meta_path}")

    return content


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Tasmota Commands.md")
    parser.add_argument("--version", required=True, help="Tasmota version the docs describe, e.g. 15.2.0")
    parser.add_argument("--date", default=date.today().isoformat(), help="date tag for the file name")
    args = parser.parse_args()
    fetch_and_save(args.version, args.date)
