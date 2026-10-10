"""Loads eval cases (the emails) and their hand-written expected outputs.

Two splits, one YAML file per case:
- dev/   the 10 cases used while building (also the demo inbox); prompts may be tuned on these
- test/  30 held-out cases; never used to tune prompts
Cases live in <split>/cases/, labels in <split>/expected/. Nothing in app/ reads the labels.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
SPLITS = ("dev", "test")


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    sender: str
    subject: str
    received_at: date
    body: str
    attachments: list[dict[str, str]] = field(default_factory=list)
    demo: bool = False
    split: str = "dev"


def load_cases(split: str = "dev") -> list[Case]:
    cases = []
    for path in sorted((EVAL_DIR / split / "cases").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.append(
            Case(
                id=raw["id"],
                title=raw["title"],
                sender=raw["sender"],
                subject=raw["subject"],
                received_at=date.fromisoformat(str(raw["received_at"])),
                body=raw["body"],
                attachments=raw.get("attachments") or [],
                demo=bool(raw.get("demo", False)),
                split=split,
            )
        )
    return cases


def load_expected(case_id: str) -> dict[str, Any]:
    for split in SPLITS:
        path = EVAL_DIR / split / "expected" / f"{case_id}.yaml"
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"No label for {case_id}")
