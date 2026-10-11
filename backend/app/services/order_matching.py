"""Which order does an email belong to? A scored match instead of an exact PO lookup.

Signals and weights (an email can match an order with or without a PO number):
  same PO base number                       +0.60
  the order's PO number appears in the email  +0.50  (when the email's own PO is missing)
  same style                                 +0.30
  same buyer                                 +0.25
  delivery date within 45 days               +0.15
  different style                            -0.30
A different PO number rules the order out: it is another order.

At or above AUTO_MATCH the email is matched; between ASK and AUTO_MATCH a person is
asked "Is this a revision of PO X?"; below ASK a new order is created.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order
from app.services.normalise import split_po_revision

AUTO_MATCH = 0.6
ASK = 0.35
_DATE_WINDOW_DAYS = 45
_LEGAL = {"gmbh", "ltd", "inc", "sas", "sarl", "llc", "bv", "pty", "co", "limited", "plc", "ag", "sa", "sl",
          "kk", "aps", "as", "srl", "spa"}


def po_key(po_number: str | None) -> str | None:
    """Base PO number without revision suffix, spacing or case: the order's identity."""
    if not po_number:
        return None
    base, _ = split_po_revision(po_number)
    return re.sub(r"\s+", "", base).casefold()


def _words(text: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").casefold().replace("&", " "))
    return {w for w in words if w not in _LEGAL}


def same_buyer(a: str | None, b: str | None) -> bool:
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def _style_key(style: str | None) -> str | None:
    return re.sub(r"[^a-z0-9]", "", style.casefold()) if style else None


def po_mentioned(po_number: str, text: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + r"\s*".join(map(re.escape, re.sub(r"\s+", "", po_number))) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


@dataclass
class Candidate:
    order: Order
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    decision: str  # match | ask | new
    best: Candidate | None = None

    @property
    def order(self) -> Order | None:
        return self.best.order if self.best and self.decision == "match" else None


def score_order(order: Order, update: dict, text: str) -> Candidate | None:
    data = order.versions[-1].data if order.versions else {}
    reasons: list[str] = []
    score = 0.0
    email_po, order_po = po_key(update.get("po_number")), po_key(order.po_number)
    if email_po and order_po:
        if email_po != order_po:
            return None
        score += 0.6
        reasons.append(f"same PO number {order.po_number}")
    elif order.po_number and po_mentioned(order.po_number, text):
        score += 0.5
        reasons.append(f"PO {order.po_number} is mentioned in the email")

    email_style, order_style = _style_key(update.get("style")), _style_key(data.get("style") or order.style)
    if email_style and order_style:
        if email_style == order_style:
            score += 0.3
            reasons.append(f"same style {order.style or data.get('style')}")
        elif email_style != _style_key(order.po_number):
            # (a style equal to the order's PO number is the order reference read as the style)
            score -= 0.3
            reasons.append("different style")
    if same_buyer(update.get("buyer"), order.buyer):
        score += 0.25
        reasons.append(f"same buyer {order.buyer}")
    if update.get("delivery_date") and data.get("delivery_date"):
        gap = abs((date.fromisoformat(update["delivery_date"]) - date.fromisoformat(data["delivery_date"])).days)
        if gap <= _DATE_WINDOW_DAYS:
            score += 0.15
            reasons.append(f"delivery {gap} days apart")
    return Candidate(order=order, score=round(score, 2), reasons=reasons)


def match_order(session: Session, update: dict, text: str) -> MatchResult:
    candidates = [c for o in session.scalars(select(Order)) if (c := score_order(o, update, text)) is not None]
    if not candidates:
        return MatchResult(decision="new")
    best = max(candidates, key=lambda c: c.score)
    if best.score >= AUTO_MATCH:
        return MatchResult(decision="match", best=best)
    if best.score >= ASK:
        return MatchResult(decision="ask", best=best)
    return MatchResult(decision="new", best=best)
