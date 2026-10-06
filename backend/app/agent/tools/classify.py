from app.llm.prompts import classify as prompt
from app.llm.prompts.common import email_messages
from app.llm.router import LLMRouter
from app.llm.structured import complete_structured
from app.llm.tasks import TaskType
from app.schemas.extraction import Classification


def classify_email(router: LLMRouter, email_text: str, *, run_id: int | None = None) -> Classification:
    return complete_structured(
        router,
        TaskType.CLASSIFY,
        email_messages(prompt.SYSTEM, email_text),
        Classification,
        max_tokens=400,
        run_id=run_id,
    )
