#!/usr/bin/env bash
# Nightly SQLite backup, run by cron (see setup.sh). Keeps the last 7 days.
# Uses SQLite's online backup API inside the api container, so it is safe while the app runs.
# Backups live in the same Docker volume as the database: /data/backups/exportagent-YYYY-MM-DD.db
set -euo pipefail
cd "$(dirname "$0")"

docker compose exec -T api python - <<'EOF'
import datetime, pathlib, sqlite3

folder = pathlib.Path("/data/backups")
folder.mkdir(exist_ok=True)
target = folder / f"exportagent-{datetime.date.today().isoformat()}.db"
source = sqlite3.connect("/data/exportagent.db")
copy = sqlite3.connect(target)
with copy:
    source.backup(copy)
copy.close()
source.close()

backups = sorted(folder.glob("exportagent-*.db"))
for old in backups[:-7]:
    old.unlink()
print(f"backup ok: {target.name} ({target.stat().st_size} bytes), kept {min(len(backups), 7)}")
EOF
