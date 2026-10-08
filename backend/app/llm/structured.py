"""JSON output validated with Pydantic: one retry with the error, then give up."""

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.router import LLMError, LLMRouter
from app.llm.tasks import TaskType

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StructuredOutputError(LLMError):
    """The model's reply failed validation twice; the item goes to human review."""


def _json_block(text: str) -> str:
    # Tolerate code fences or stray prose around the object.
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def complete_structured(
    router: LLMRouter,
    task: TaskType,
    messages: list[dict[str, Any]],
    schema: type[SchemaT],
    *,
    max_tokens: int,
    reasoning: bool | None = None,
    run_id: int | None = None,
) -> SchemaT:
    messages = list(messages)
    error = ""
    for _attempt in range(2):
        result = router.complete(
            task, messages, max_tokens=max_tokens, temperature=0, reasoning=reasoning, run_id=run_id
        )
        content = result.content or ""
        try:
            return schema.model_validate_json(_json_block(content))
        except ValidationError as exc:
            error = str(exc)
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "That reply failed validation:\n"
                        f"{error}\n"
                        "Reply again with only the corrected JSON object."
                    ),
                },
            ]
    raise StructuredOutputError(
        f"{task.value}: reply failed {schema.__name__} validation after one retry: {error}"
    )
