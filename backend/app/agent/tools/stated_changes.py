from app.llm.prompts import changes as prompt
from app.llm.prompts.common import email_messages
from app.llm.router import LLMRouter
from app.llm.structured import complete_structured
from app.llm.tasks import TaskType
from app.schemas.orders import StatedChange, StatedChanges


def extract_stated_changes(
    router: LLMRouter, email_text: str, *, run_id: int | None = None
) -> list[StatedChange]:
    """Changes the email spells out with old and new values (e.g. in a reply thread).

    Used to rebuild the previous version of an order the store has not seen yet.
    """
    result = complete_structured(
        router,
        TaskType.CHANGE_DETECTION,
        email_messages(prompt.SYSTEM, email_text),
        StatedChanges,
        max_tokens=600,
        run_id=run_id,
    )
    return result.changes
