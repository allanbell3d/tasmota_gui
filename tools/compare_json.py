"""Compare two command library JSON files.

Usage:
    git show HEAD~1:assets/commands/tasmota_commands.json > old.json
    python tools/compare_json.py old.json [assets/commands/tasmota_commands.json]
"""
import argparse
import json
from pathlib import Path

DEFAULT_NEW = Path(__file__).resolve().parents[1] / "assets" / "commands" / "tasmota_commands.json"


def _names(data):
    return {cmd.get('Command') or cmd.get('command') for cmd in data}


def main():
    parser = argparse.ArgumentParser(description="Compare two tasmota_commands.json files")
    parser.add_argument("old", type=Path, help="reference/backup JSON")
    parser.add_argument("new", type=Path, nargs="?", default=DEFAULT_NEW, help="JSON to check (default: bundled)")
    args = parser.parse_args()

    new_data = json.loads(args.new.read_text(encoding='utf-8'))
    old_data = json.loads(args.old.read_text(encoding='utf-8'))

    print(f"New file: {len(new_data)} commands")
    print(f"Old file: {len(old_data)} commands")

    old_cats = {}
    for cmd in old_data:
        cat = cmd.get('category', 'Unknown')
        old_cats[cat] = old_cats.get(cat, 0) + 1

    print("\nOld categories:")
    for cat, count in sorted(old_cats.items()):
        print(f"  {cat}: {count}")

    new_names = _names(new_data)
    old_names = _names(old_data)
    for label, names in (("in old but NOT in new", old_names - new_names), ("in new but NOT in old", new_names - old_names)):
        print(f"\nCommands {label} ({len(names)}):")
        for name in sorted(names)[:20]:
            print(f"  {name}")
        if len(names) > 20:
            print(f"  ... and {len(names) - 20} more")


if __name__ == "__main__":
    main()
