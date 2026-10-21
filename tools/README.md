# Tools Directory

This directory contains utility scripts for maintaining the Tasmota command library. These tools are used to fetch, parse, and compare command documentation from the official Tasmota repository.

## Tools Overview

### fetch_docs.py

Downloads the official Tasmota Commands documentation from GitHub.

**Usage:**
```bash
python tools/fetch_docs.py --version 15.2.0 [--date 2026-01-05]
```

**What it does:**
1. Fetches `Commands.md` from the Tasmota docs repository
2. Saves the raw markdown to `assets/reference/tasmota/`
3. Creates a metadata JSON file with fetch timestamp and version info

**Arguments:** `--version` (required) is the Tasmota version the docs describe;
`--date` (default: today) is used in the file names. Output goes to
`assets/reference/tasmota/` relative to the repository.

---

### parse_tasmota_docs.py

Parses the downloaded Tasmota documentation to generate the command library JSON file.

**Usage:**
```bash
python tools/parse_tasmota_docs.py                     # newest commands_raw_*.md
python tools/parse_tasmota_docs.py --input FILE --output FILE
```

**What it does:**
1. Reads the raw markdown from `assets/reference/tasmota/`
2. Extracts command names, parameters, and descriptions
3. Identifies default values from various markdown patterns
4. Generates `assets/commands/tasmota_commands.json`

**Note:** The version and date are carried by the raw file name
(`commands_raw_<date>_v<version>.md`), not by the parser.

---

### compare_json.py

Compares two command library JSON files to identify differences.

**Usage:**
```bash
git show HEAD~1:assets/commands/tasmota_commands.json > old.json
python tools/compare_json.py old.json [new.json]
```

**What it does:**
1. Loads the current `tasmota_commands.json` (or the second argument)
2. Loads the reference copy given as the first argument
3. Reports:
   - Total command counts
   - Category breakdown
   - Commands missing from one file
   - Commands added in the other file

**Useful for:** Verifying updates to the command library haven't accidentally removed commands.

---

### migrate_settings_from_git.py

One-off migration for v0.3.0. Older versions hard-coded personal values (IP
ranges, MQTT/rule backlog commands) in `src/tasmota/constants.py`. This tool
reads the newest commit that still has them (`git show`, parsed with
`ast.literal_eval`, nothing is executed) and writes
`.private/tasmota_settings.json`. Run it before rewriting the git history.

```bash
python tools/migrate_settings_from_git.py [--ref COMMIT] [--force]
```

---

## Typical Workflow

When updating the command library for a new Tasmota version:

1. **Run fetch_docs.py** with the new `--version` to download the documentation
2. **Run parse_tasmota_docs.py** to regenerate `tasmota_commands.json`
3. **Adjust the parser** only if the documentation format changed
4. **Run compare_json.py** to verify changes look correct
5. **Run `pytest -q`** and test the app to ensure commands load properly

---

## Output Locations

| Tool | Output |
|------|--------|
| fetch_docs.py | `assets/reference/tasmota/commands_raw_*.md` |
| parse_tasmota_docs.py | `assets/commands/tasmota_commands.json` |
| migrate_settings_from_git.py | `.private/tasmota_settings.json` |
| compare_json.py | Console output only |
