from app.llm.prompts import extract as prompt
from app.llm.prompts.common import email_messages
from app.llm.router import LLMRouter
from app.llm.structured import complete_structured
from app.llm.tasks import TaskType
from app.schemas.extraction import POExtraction


def extract_po_fields(router: LLMRouter, email_text: str, *, run_id: int | None = None) -> POExtraction:
    return complete_structured(
        router,
        TaskType.EXTRACT,
        email_messages(prompt.SYSTEM, email_text),
        POExtraction,
        max_tokens=1500,
        # Thinking off: with it on, Nemotron Nano spends the whole budget reasoning and returns no JSON.
        reasoning=False,
        run_id=run_id,
    )
