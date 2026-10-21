"""Recreate .private/tasmota_settings.json from the old hard-coded constants.

Up to v0.2.2 personal values (IP ranges, MQTT/rules backlog commands) were
hard-coded in src/tasmota/constants.py. v0.3.0 keeps them in the git-ignored
private settings file instead. Run this once, BEFORE rewriting or deleting
the git history, to carry those values over:

    python tools/migrate_settings_from_git.py            # newest commit that still has them
    python tools/migrate_settings_from_git.py --ref 1231279 --force

The old file is read with ``git show`` and parsed with ``ast.literal_eval``
(nothing from it is executed). An existing settings file is only replaced
with --force.
"""
import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = "src/tasmota/constants.py"
TARGET = ROOT / ".private" / "tasmota_settings.json"
WANTED = ("DEFAULT_IP_RANGES", "COMMAND_LIBRARY", "DEFAULT_THREADS", "DEFAULT_TIMEOUT", "DEFAULT_RETRIES")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def _literals(source: str) -> dict:
    values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in WANTED:
                values[name] = ast.literal_eval(node.value)
    return values


def _find_values(ref):
    refs = [ref] if ref else _git("log", "--all", "--format=%H", "--", CONSTANTS).split()
    for sha in refs:
        try:
            values = _literals(_git("show", f"{sha}:{CONSTANTS}"))
        except (subprocess.CalledProcessError, SyntaxError, ValueError):
            continue
        if "COMMAND_LIBRARY" in values:
            return sha, values
    return None, {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate hard-coded settings into .private/")
    parser.add_argument("--ref", help="commit to read constants.py from (default: newest that has them)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing settings file")
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        print(f"{TARGET} already exists; use --force to replace it.")
        return 1
    sha, values = _find_values(args.ref)
    if not values:
        print("No commit with the old COMMAND_LIBRARY found in this repository's history.")
        return 1

    library = values["COMMAND_LIBRARY"]
    settings = {
        "ip_ranges": values.get("DEFAULT_IP_RANGES", ""),
        "commands": [command.strip() for command, _ in library if command.strip()],
        "threads": values.get("DEFAULT_THREADS", 100),
        "timeout": float(values.get("DEFAULT_TIMEOUT", 1)),
        "retries": values.get("DEFAULT_RETRIES", 1),
        "info_mode": "lite",
        "output_dir": "",
        "web_password": "",
        "_command_notes": {command.strip(): note for command, note in library},
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET} from commit {sha[:10]} ({len(settings['commands'])} commands).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
