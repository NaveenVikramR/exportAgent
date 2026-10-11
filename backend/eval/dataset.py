"""Loads eval cases (the emails) and their hand-written expected outputs.

Splits, one file per case (YAML, or JSON, which the YAML parser reads as it is):
- dev/      the cases used while building (the first ten are also the demo inbox); fixes are made on these
- test/     TEST v1, 30 cases; held out until Milestone 7, now seen (its failures led to new DEV cases)
- test_v2/  held-out cases written outside this codebase (see eval/TEST_V2_SPEC.md)
Cases live in <split>/cases/, labels in <split>/expected/. Nothing in app/ reads the labels.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
SPLITS = ("dev", "test", "test_v2")
_SUFFIXES = (".yaml", ".json")


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
    folder = EVAL_DIR / split / "cases"
    for path in sorted(p for p in folder.glob("*") if p.suffix in _SUFFIXES):
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
        for suffix in _SUFFIXES:
            path = EVAL_DIR / split / "expected" / f"{case_id}{suffix}"
            if path.exists():
                return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"No label for {case_id}")
