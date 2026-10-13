"""Replaces everything in the configured database with the demo snapshot.

Usage (from backend/):  python -m scripts.load_demo
Works for SQLite and Postgres (DATABASE_URL). No model calls.
"""

import sys

from app.db import SessionLocal
from app.services.demo import SNAPSHOT_PATH, load_snapshot, read_snapshot


def main() -> int:
    snapshot = read_snapshot()
    if snapshot is None:
        print(f"No snapshot at {SNAPSHOT_PATH}; build it with python -m scripts.build_demo")
        return 1
    with SessionLocal() as session:
        counts = load_snapshot(session, snapshot)
    print("Loaded demo: " + ", ".join(f"{name} {count}" for name, count in counts.items() if count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
