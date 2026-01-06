import json
from pathlib import Path

BASE = Path(r"D:\IA\Claude\Tasmota_GUI\assets\commands")
NEW = BASE / "tasmota_commands.json"
BACKUP = BASE / "tasmota_commands - Copy.json"

with open(NEW, encoding='utf-8') as f:
    new_data = json.load(f)

with open(BACKUP, encoding='utf-8') as f:
    backup_data = json.load(f)

print(f"New file: {len(new_data)} commands")
print(f"Backup file: {len(backup_data)} commands")

# Categories in backup
backup_cats = {}
for cmd in backup_data:
    cat = cmd.get('category', 'Unknown')
    backup_cats[cat] = backup_cats.get(cat, 0) + 1

print("\nBackup categories:")
for cat, count in sorted(backup_cats.items()):
    print(f"  {cat}: {count}")

# Commands in backup but not in new
new_names = {cmd['Command'] for cmd in new_data}
backup_names = {cmd['Command'] for cmd in backup_data}

missing = backup_names - new_names
extra = new_names - backup_names

print(f"\nCommands in backup but NOT in new ({len(missing)}):")
for name in sorted(missing)[:20]:
    print(f"  {name}")
if len(missing) > 20:
    print(f"  ... and {len(missing) - 20} more")

print(f"\nCommands in new but NOT in backup ({len(extra)}):")
for name in sorted(extra)[:20]:
    print(f"  {name}")
if len(extra) > 20:
    print(f"  ... and {len(extra) - 20} more")
