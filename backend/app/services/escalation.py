"""Escalation routing: Nano extracts first; fields that fail a Python check go to Super.

Only the failing field is re-extracted, and Super's answer is kept only if the
same check passes on it. Every escalation is recorded with its cost.
"""

import re
from decimal import Decimal

from app.llm.prompts import escalate as prompt
from app.llm.prompts.common import email_messages
from app.llm.router import LLMError, LLMResult, LLMRouter, SpendCapExceeded
from app.llm.structured import complete_structured
from app.llm.tasks import TaskType
from app.schemas.extraction import (
    SCALAR_FIELDS,
    EmailCategory,
    Escalation,
    POExtraction,
    ReviewedExtraction,
)
from app.services.review import review_extraction

_FLAG_REASONS = {
    "quantity_mismatch": "size_total_mismatch",
    "evidence_not_found": "source_quote_missing",
    "evidence_mismatch": "source_quote_missing",
}


# Header words for "colour" and "size" in the languages buyers write POs in.
_COLOUR_WORDS = r"colou?rs?|coloris|couleurs?|colores|farben?|kleur(?:en)?|colori|renk"
_SIZE_WORDS = r"sizes?|tailles?|tallas?|gr(?:ö|oe)(?:ss|ß)en?|maten|taglie"
_HEADER_WORD = re.compile(rf"^(?:{_COLOUR_WORDS}|{_SIZE_WORDS})$", re.IGNORECASE)


def has_size_table(text: str) -> bool:
    """A table header (colour or size column first, in any of several languages) followed by a row of quantities.

    Covers "Colour  S  M  L  Total", "Kleur/Colour ...", "Coloris / Colour 4A 6A", "Farbe S M L Gesamt",
    and tables with sizes as rows ("Size | Navy | White").
    """
    lines = [line for line in text.splitlines() if line.strip()]
    for header, row in zip(lines, lines[1:]):
        # A table header is a list of column names, not a sentence like "Colours and quantities: ..."
        if ":" in header:
            continue
        tokens = [t for t in re.split(r"[\s|/,;]+", header) if t]
        if len(tokens) >= 3 and any(_HEADER_WORD.match(t) for t in tokens[:3]):
            if len(re.findall(r"\d[\d,.]*", row)) >= 2:
                return True
    return False


def escalation_targets(reviewed: ReviewedExtraction, source_text: str) -> list[tuple[str, str]]:
    """(field, reason) pairs to re-extract, at most one reason per field."""
    targets: dict[str, str] = {}
    fields = reviewed.fields
    if has_size_table(source_text) and not any(item.sizes for item in fields.line_items):
        targets["line_items"] = "size_table_not_extracted"
    for flag in reviewed.review:
        reason = _FLAG_REASONS.get(flag.reason)
        if reason is None:
            continue
        # Sizes that do not add up are fixed by re-reading the line items, not the total.
        field = "line_items" if reason == "size_total_mismatch" else flag.field
        if field == "line_items" or field in SCALAR_FIELDS:
            targets.setdefault(field, reason)
    return list(targets.items())


def _value(fields: POExtraction, field: str):
    value = getattr(fields, field)
    return [item.model_dump(mode="json") for item in value] if field == "line_items" else value.model_dump(mode="json")["value"]


def escalate(
    router: LLMRouter,
    reviewed: ReviewedExtraction,
    source_text: str,
    category: EmailCategory,
    threshold: float,
) -> ReviewedExtraction:
    targets = escalation_targets(reviewed, source_text)
    if not targets:
        return reviewed

    current = reviewed.fields
    escalations: list[Escalation] = []
    for field, reason in targets:
        results: list[LLMResult] = []
        before = _value(current, field)
        outcome, after = "unresolved", None
        try:
            partial = complete_structured(
                router,
                TaskType.EXTRACT_ESCALATION,
                email_messages(prompt.system_prompt(field, reason), source_text),
                POExtraction,
                max_tokens=1500,
                reasoning=False,
                detail=f"escalation: {field} ({reason})",
                collect=results,
            )
        except SpendCapExceeded:
            outcome = "skipped_spend_cap"
        except LLMError:
            outcome = "failed"
        else:
            candidate = current.model_copy(deep=True)
            setattr(candidate, field, getattr(partial, field))
            after = _value(candidate, field)
            recheck = review_extraction(candidate, source_text, category, threshold)
            if (field, reason) not in escalation_targets(recheck, source_text):
                current, outcome = candidate, "resolved"

        escalations.append(
            Escalation(
                field=field,
                reason=reason,
                model=results[-1].model if results else router.settings.model_for(router.tier_for(TaskType.EXTRACT_ESCALATION)),
                calls=len(results),
                input_tokens=sum(r.input_tokens for r in results),
                output_tokens=sum(r.output_tokens for r in results),
                cost_usd=sum((r.cost_usd for r in results), Decimal("0")),
                outcome=outcome,
                before=before,
                after=after,
            )
        )

    final = review_extraction(current, source_text, category, threshold)
    final.escalations = escalations
    return final
