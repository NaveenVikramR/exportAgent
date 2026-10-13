"""Builds the demo snapshot (backend/demo/snapshot.json) with live model calls.

Usage (from backend/):  python -m scripts.build_demo
1. A fresh SQLite database in backend/demo/build.db; the search cache is copied from the
   main database, so the compliance and buyer checks reuse earlier Tavily results (copied
   searches the demo did not use are dropped again before the export).
2. The demo emails (DEV cases marked `demo: true`) are seeded, analysed, assessed and
   drafted in arrival order, with the response cache on: every model response is stored.
3. The whole database, cached responses included, is written to backend/demo/snapshot.json.

Load it with `python -m scripts.load_demo` or at API start-up (DEMO_SEED_ON_EMPTY=true).
Cost: about $0.10 per build.
"""

import json
import os
import subprocess
import sys

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.config import BACKEND_DIR, get_settings
from app.db import Base
from app.models import SearchCache
from app.services.demo import SNAPSHOT_PATH, export_snapshot

BUILD_DB = BACKEND_DIR / "demo" / "build.db"


def main() -> int:
    BUILD_DB.parent.mkdir(exist_ok=True)
    if BUILD_DB.exists():
        BUILD_DB.unlink()
    url = f"sqlite:///{BUILD_DB.as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    Build = sessionmaker(bind=engine)

    main_engine = create_engine(get_settings().database_url)
    with sessionmaker(bind=main_engine)() as main, Build() as build:
        copied = set()
        for row in main.scalars(select(SearchCache)):
            build.merge(SearchCache(key=row.key, query=row.query, response=row.response))
            copied.add(row.key)
        build.commit()
    main_engine.dispose()

    env = {**os.environ, "DATABASE_URL": url, "LLM_CACHE_ENABLED": "true", "LLM_MODE": "live"}
    result = subprocess.run([sys.executable, "-m", "scripts.seed", "--analyse", "--agent", "--drafts"], env=env)
    if result.returncode != 0:
        return result.returncode

    with Build() as build:
        # Keep only searches made during this build. A search answered from the copied cache is
        # dropped too; re-running that demo step then asks Tavily again.
        used = {row.key for row in build.scalars(select(SearchCache)) if row.key not in copied}
        build.execute(delete(SearchCache).where(SearchCache.key.not_in(used)))
        build.commit()
        snapshot = export_snapshot(build)
    engine.dispose()
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = {name: len(rows) for name, rows in snapshot["tables"].items()}
    print(f"Written {SNAPSHOT_PATH} ({SNAPSHOT_PATH.stat().st_size // 1024} KB): {sizes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
