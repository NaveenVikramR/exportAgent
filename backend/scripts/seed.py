"""Loads the demo emails into the inbox. Safe to re-run: existing emails are left alone.

Usage (from backend/):  python -m scripts.seed [--analyse] [--agent]
--analyse also runs classification and extraction, so results are stored up front.
--agent then runs the risk agent on every email linked to an order.
"""

import argparse
import sys
from datetime import UTC, datetime, time

from sqlalchemy import select

from app.agent.loop import run_agent
from app.db import SessionLocal
from app.llm.router import SpendCapExceeded, get_router
from app.models import AgentRun, Email, EmailAttachment
from app.services.analysis import analyse_email
from eval.dataset import load_cases


def _assess(session, email: Email, router) -> None:
    run = run_agent(session, email, router)
    flags = (run.result or {}).get("flags", [])
    found = ", ".join(f"{f['severity']} {f['category']}" for f in flags) or "no flags"
    print(f"  agent: {run.status}, {run.rounds} rounds, {found}" + (f" ({run.error})" if run.error else ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyse", action="store_true")
    parser.add_argument("--agent", action="store_true")
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
            pending = session.scalars(
                select(Email).where(Email.classification.is_(None)).order_by(Email.received_at, Email.id)
            ).all()
            for email in pending:
                try:
                    analyse_email(session, email, router)
                    print(f"{email.external_id}: {email.status}" + (f" ({email.analysis_error})" if email.analysis_error else ""))
                    # Assess each email as it arrives, so it sees the order as it was then.
                    if args.agent and email.order_id is not None:
                        _assess(session, email, router)
                except SpendCapExceeded as exc:
                    print(f"Stopped: {exc}")
                    return 1

        if args.agent:
            router = get_router()
            assessed = set(session.scalars(select(AgentRun.email_id)))
            emails = session.scalars(
                select(Email).where(Email.order_id.is_not(None)).order_by(Email.received_at, Email.id)
            ).all()
            for email in emails:
                if email.id in assessed:
                    continue
                try:
                    _assess(session, email, router)
                except SpendCapExceeded as exc:
                    print(f"Stopped: {exc}")
                    return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
