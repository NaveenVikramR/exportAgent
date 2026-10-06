"""Loads eval cases (the emails) and their hand-written expected outputs.

Cases live in eval/cases/, labels in eval/expected/, one YAML file per case.
Nothing in app/ reads the labels.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
CASES_DIR = EVAL_DIR / "cases"
EXPECTED_DIR = EVAL_DIR / "expected"


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


def load_cases() -> list[Case]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.append(
            Case(
                id=raw["id"],
                title=raw["title"],
                sender=raw["sender"],
                subject=raw["subject"],
                received_at=date.fromisoformat(raw["received_at"]),
                body=raw["body"],
                attachments=raw.get("attachments") or [],
                demo=bool(raw.get("demo", False)),
            )
        )
    return cases


def load_expected(case_id: str) -> dict[str, Any]:
    path = EXPECTED_DIR / f"{case_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
