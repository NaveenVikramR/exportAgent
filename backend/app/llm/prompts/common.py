from typing import Any

EMAIL_OPEN = "<email>"
EMAIL_CLOSE = "</email>"


def email_messages(system: str, email_text: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{EMAIL_OPEN}\n{email_text}\n{EMAIL_CLOSE}"},
    ]
