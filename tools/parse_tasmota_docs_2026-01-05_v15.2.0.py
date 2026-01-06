"""
Parse Tasmota Commands documentation to generate tasmota_commands.json
Version: 15.2.0
Date: 2026-01-05
"""

import re
import json
import os
from pathlib import Path

# Paths
BASE_DIR = Path(r"D:\IA\Claude\Tasmota_GUI")
INPUT_FILE = BASE_DIR / "assets" / "reference" / "tasmota" / "commands_raw_2026-01-05_v15.2.0.md"
OUTPUT_FILE = BASE_DIR / "assets" / "commands" / "tasmota_commands.json"

# Regex patterns
SECTION_PATTERN = re.compile(r'^###\s+(.+?)(?:\s*\{.*\})?$', re.MULTILINE)
COMMAND_ROW_PATTERN = re.compile(
    r'^([A-Za-z0-9_<>\\]+(?:<[^>]*>)?)'  # Command name (may have <x> suffix)
    r'(?:<a\s+class="cmnd"[^>]*>.*?</a>)?'  # Optional anchor tag
    r'\|'  # Table delimiter
    r'(.+)$',  # Parameters/description
    re.MULTILINE
)
# Default value patterns
DEFAULT_PATTERNS = [
    re.compile(r'\*\(default\s*=\s*`([^`]+)`\)\*'),  # *(default = `value`)*
    re.compile(r'\*\(default\)\*'),  # *(default)*
    re.compile(r'_\(default\s*=\s*`?([^)`]+)`?\)_'),  # _(default = value)_
    re.compile(r'_\(default\)_'),  # _(default)_
    re.compile(r'\(default\s*=\s*([^)]+)\)'),  # (default = value)
]


def normalize_description(raw: str) -> str:
    """Convert raw markdown/HTML description to clean text."""
    text = raw

    # Remove anchor tags
    text = re.sub(r'<a\s+class="cmnd"[^>]*>.*?</a>', '', text)
    text = re.sub(r'<a\s+[^>]*>([^<]*)</a>', r'\1', text)  # Keep link text

    # Convert <BR> to newlines
    text = text.replace('<BR>', '\n')
    text = text.replace('<br>', '\n')
    text = text.replace('<br/>', '\n')
    text = text.replace('<br />', '\n')

    # Convert markdown links [text](url) - keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Clean up escaped characters
    text = text.replace('\\|', '|')
    text = text.replace('<x\\>', '<x>')
    text = text.replace(r'<x\>', '<x>')

    # Remove backticks but keep content
    text = text.replace('`', '')

    # Clean up markdown formatting
    text = text.replace('**(', '(')
    text = text.replace(')**', ')')
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** -> bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # *italic* -> italic
    text = re.sub(r'_([^_]+)_', r'\1', text)  # _italic_ -> italic

    # Normalize whitespace
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if line:
            lines.append(line)
    text = '\n'.join(lines)

    return text.strip()


def extract_default(description: str) -> str:
    """Extract default value from description text."""
    # Pattern 1: *(default = `value`)*
    match = re.search(r'\*\(default\s*=\s*`([^`]+)`\)\*', description)
    if match:
        return match.group(1)

    # Pattern 2: _(default = `value`)_
    match = re.search(r'_\(default\s*=\s*`([^`]+)`\)_', description)
    if match:
        return match.group(1)

    # Pattern 3: (default = value)
    match = re.search(r'\(default\s*=\s*([^)]+)\)', description, re.IGNORECASE)
    if match:
        val = match.group(1).strip().strip('`').strip('"').strip("'").replace('`', '')
        return val

    # Pattern 4: Look for "= X (default)" or "= X *(default)*"
    match = re.search(r'`(\d+)`[^`]*\*?\(default\)\*?', description)
    if match:
        return match.group(1)

    # Pattern 5: Look for value followed by (default) on same line
    for line in description.split('<BR>'):
        if '(default)' in line.lower():
            # Try to extract the value
            val_match = re.search(r'`([^`]+)`', line)
            if val_match:
                return val_match.group(1)
            # Look for pattern like "0 = ... (default)"
            val_match = re.search(r'^`?(\d+)`?\s*[=/]', line.strip())
            if val_match:
                return val_match.group(1)

    return ""


def parse_markdown(content: str) -> list:
    """Parse the markdown content and extract all commands."""
    commands = []

    # Find all section headers and their positions
    sections = []
    for match in SECTION_PATTERN.finditer(content):
        section_name = match.group(1).strip()
        # Skip non-command sections
        if section_name.lower() in ['how to use commands', 'commands list']:
            continue
        sections.append((section_name, match.end()))

    # Add end position
    sections.append(('END', len(content)))

    # Process each section
    for i in range(len(sections) - 1):
        category = sections[i][0]
        start_pos = sections[i][1]
        end_pos = sections[i + 1][1]

        section_content = content[start_pos:end_pos]

        # Find the table in this section
        # Tables start with "Command|Parameters" header (may have extra content after Parameters)
        # Handle various separator formats: :---|:---, :---:|:---, :--- |:---
        table_match = re.search(r'Command\|Parameters[^\n]*\n:---:?\s*\|:---:?\s*\n', section_content)
        if not table_match:
            continue

        table_start = table_match.end()

        # Find where table ends (next section header or empty lines)
        table_end = len(section_content)
        next_section = re.search(r'\n###\s+', section_content[table_start:])
        if next_section:
            table_end = table_start + next_section.start()

        table_content = section_content[table_start:table_end]

        # Parse table rows
        for line in table_content.split('\n'):
            line = line.strip()
            if not line or line.startswith(':---'):
                continue

            # Split on first | to get command and parameters
            parts = line.split('|', 1)
            if len(parts) != 2:
                continue

            command_part = parts[0].strip()
            params_part = parts[1].strip()

            # Skip "See also" entries - they're not commands
            if command_part.lower().startswith('see also'):
                continue

            # Extract command name (remove anchor tags)
            command_name = re.sub(r'<a\s+[^>]*>.*?</a>', '', command_part).strip()

            # Clean up command name
            command_name = command_name.replace('<x\\>', '<x>')
            command_name = command_name.replace('\\', '')
            command_name = command_name.replace('`', '')  # Remove backticks

            if not command_name:
                continue

            # Handle multiple command names separated by <BR> (aliases)
            # e.g., "BuzzerActive<BR>SetOption67" -> two commands
            command_names = [n.strip() for n in command_name.split('<BR>') if n.strip()]

            # Filter out invalid command names (continuation text, not actual commands)
            valid_names = []
            for name in command_names:
                # Skip if starts with special chars or lowercase (not a command)
                if name.startswith('*') or name.startswith('(') or name.startswith('<'):
                    continue
                # Skip if it's clearly descriptive text (starts with lowercase or has spaces)
                if name[0].islower() or ' ' in name:
                    continue
                # Skip if it doesn't look like a command name (should start with letter)
                if not name[0].isalpha():
                    continue
                valid_names.append(name)
            command_names = valid_names

            if not command_names:
                continue

            # Extract default value
            default_value = extract_default(params_part)

            # Normalize description
            description = normalize_description(params_part)

            # Add each command (may be multiple if aliases exist)
            for cmd_name in command_names:
                # Add documentation link
                cmd_anchor = cmd_name.lower().replace('<', '').replace('>', '').replace('x', 'x')
                full_desc = description + f"\n\nDocumentation: [{cmd_name}](https://tasmota.github.io/docs/Commands/#{cmd_anchor})"

                commands.append({
                    "Command": cmd_name,
                    "Value": default_value,
                    "Description": full_desc,
                    "category": category
                })

    return commands


def main():
    print(f"Reading: {INPUT_FILE}")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"File size: {len(content)} characters")

    commands = parse_markdown(content)

    print(f"Parsed {len(commands)} commands")

    # Show category breakdown
    categories = {}
    for cmd in commands:
        cat = cmd['category']
        categories[cat] = categories.get(cat, 0) + 1

    print("\nCategories:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    # Save to JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(commands, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {OUTPUT_FILE}")

    # Show some sample commands for verification
    print("\nSample commands:")
    for cmd in commands[:3]:
        print(f"  {cmd['Command']}: Value={cmd['Value']!r}")


if __name__ == "__main__":
    main()
