"""Rebuilds the local SQLite demo database from the seed emails, keeping the LLM and search caches.

Usage (from backend/):  python -m scripts.rebuild_demo
Runs: migrate a fresh database, restore the caches, then seed --analyse --agent --drafts.
Identical model requests are then served from the cache, so a rebuild costs only what changed.
"""

import os
import subprocess
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import LLMCache, SearchCache


def main() -> int:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        print("Only for the local SQLite demo database.")
        return 1
    path = url.removeprefix("sqlite:///")

    engine = create_engine(url)
    with sessionmaker(bind=engine)() as session:
        llm = [(r.key, r.model, r.response) for r in session.scalars(select(LLMCache))]
        search = [(r.key, r.query, r.response) for r in session.scalars(select(SearchCache))]
    engine.dispose()
    print(f"Keeping {len(llm)} cached model responses and {len(search)} cached searches.")

    os.remove(path)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    engine = create_engine(url)
    with sessionmaker(bind=engine)() as session:
        session.add_all(LLMCache(key=k, model=m, response=r) for k, m, r in llm)
        session.add_all(SearchCache(key=k, query=q, response=r) for k, q, r in search)
        session.commit()
    engine.dispose()

    return subprocess.run([sys.executable, "-m", "scripts.seed", "--analyse", "--agent", "--drafts"]).returncode


if __name__ == "__main__":
    sys.exit(main())
