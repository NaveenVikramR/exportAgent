from app.llm.prompts import extract

# Why the first answer was rejected, in words the model can act on.
REASON_HINTS = {
    "size_table_not_extracted": (
        "The email contains a size table. Copy every per-size quantity from it, "
        "and the colour's total from the table's total column."
    ),
    "size_total_mismatch": (
        "A previous answer gave per-size quantities that do not add up to the stated totals. "
        "Copy only numbers written in the email; if no per-size quantities are written, leave sizes empty."
    ),
    "source_quote_missing": (
        "A previous answer quoted text that does not state this value. Quote the exact text that states it. "
        "If the email does not state it, use null."
    ),
}


def system_prompt(field: str, reason: str) -> str:
    if field == "line_items":
        shape = '{"line_items": [{"colour": <string>, "sizes": {"<size>": <integer>}, "quantity": <integer or null>, "unit_price": <string or null>}]}'
    else:
        shape = f'{{"{field}": {{"value": <value or null>, "confidence": <0 to 1>, "evidence": <exact quote or null>}}}}'
    return (
        f"{extract.SYSTEM}\n\n"
        f'This time extract ONLY the field "{field}". Reply with one JSON object and nothing else:\n'
        f"{shape}\n\n"
        f"{REASON_HINTS[reason]}"
    )
