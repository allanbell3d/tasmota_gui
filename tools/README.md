# Tools Directory

This directory contains utility scripts for maintaining the Tasmota command library. These tools are used to fetch, parse, and compare command documentation from the official Tasmota repository.

## Tools Overview

### fetch_docs.py

Downloads the official Tasmota Commands documentation from GitHub.

**Usage:**
```bash
python tools/fetch_docs.py
```

**What it does:**
1. Fetches `Commands.md` from the Tasmota docs repository
2. Saves the raw markdown to `assets/reference/tasmota/`
3. Creates a metadata JSON file with fetch timestamp and version info

**Configuration:**
- `URL`: GitHub raw URL for Commands.md
- `OUTPUT_DIR`: Where to save downloaded files
- `VERSION`: Current Tasmota version being documented
- `DATE`: Date of the fetch

---

### parse_tasmota_docs_*.py

Parses the downloaded Tasmota documentation to generate the command library JSON file.

**Usage:**
```bash
python tools/parse_tasmota_docs_2026-01-05_v15.2.0.py
```

**What it does:**
1. Reads the raw markdown from `assets/reference/tasmota/`
2. Extracts command names, parameters, and descriptions
3. Identifies default values from various markdown patterns
4. Generates `assets/commands/tasmota_commands.json`

**Note:** The filename includes the version and date to track which parser corresponds to which documentation version.

---

### compare_json.py

Compares two command library JSON files to identify differences.

**Usage:**
```bash
python tools/compare_json.py
```

**What it does:**
1. Loads the current `tasmota_commands.json`
2. Loads a backup/reference copy
3. Reports:
   - Total command counts
   - Category breakdown
   - Commands missing from one file
   - Commands added in the other file

**Useful for:** Verifying updates to the command library haven't accidentally removed commands.

---

### Commands.md

Local reference copy of Tasmota command documentation. May be used for offline parsing or as a reference during development.

---

## Typical Workflow

When updating the command library for a new Tasmota version:

1. **Update version numbers** in `fetch_docs.py`
2. **Run fetch_docs.py** to download latest documentation
3. **Create or update parser** with new version suffix
4. **Run parser** to regenerate `tasmota_commands.json`
5. **Run compare_json.py** to verify changes look correct
6. **Test the app** to ensure commands load properly

---

## Output Locations

| Tool | Output |
|------|--------|
| fetch_docs.py | `assets/reference/tasmota/commands_raw_*.md` |
| parse_*.py | `assets/commands/tasmota_commands.json` |
| compare_json.py | Console output only |
