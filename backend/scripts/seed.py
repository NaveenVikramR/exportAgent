"""Loads the demo emails into the inbox. Safe to re-run: existing emails are left alone.

Usage (from backend/):  python -m scripts.seed [--analyse]
--analyse also runs classification and extraction, so results are stored up front.
"""

import argparse
import sys
from datetime import UTC, datetime, time

from sqlalchemy import select

from app.db import SessionLocal
from app.llm.router import SpendCapExceeded, get_router
from app.models import Email, EmailAttachment
from app.services.analysis import analyse_email
from eval.dataset import load_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyse", action="store_true")
    args = parser.parse_args()

    added = 0
    with SessionLocal() as session:
        for case in load_cases():
            if not case.demo:
                continue
            if session.scalar(select(Email).where(Email.external_id == case.id)):
                continue
            session.add(
                Email(
                    external_id=case.id,
                    sender=case.sender,
                    subject=case.subject,
                    body=case.body,
                    received_at=datetime.combine(case.received_at, time(9, 0), tzinfo=UTC),
                    source="seed",
                    attachments=[
                        EmailAttachment(
                            filename=a["filename"],
                            content_type=a["content_type"],
                            text_content=a["text"],
                        )
                        for a in case.attachments
                    ],
                )
            )
            added += 1
        session.commit()
        print(f"Seeded {added} new emails.")

        if args.analyse:
            router = get_router()
            for email in session.scalars(select(Email).where(Email.classification.is_(None))):
                try:
                    analyse_email(session, email, router)
                except SpendCapExceeded as exc:
                    print(f"Stopped: {exc}")
                    return 1
                print(f"{email.external_id}: {email.status}" + (f" ({email.analysis_error})" if email.analysis_error else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
