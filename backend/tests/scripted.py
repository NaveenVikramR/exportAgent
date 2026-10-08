"""An OpenAI-shaped client that replays scripted replies, for router-level tests."""

import json
from types import SimpleNamespace


def reply(content: str | None = None, tool_calls: list[tuple[str, dict]] | None = None,
          prompt_tokens: int = 100, completion_tokens: int = 50) -> SimpleNamespace:
    calls = [
        SimpleNamespace(id=f"call_{i}_{name}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
        for i, (name, args) in enumerate(tool_calls or [])
    ]
    message = SimpleNamespace(content=content, tool_calls=calls or None)
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls" if calls else "stop")],
    )


class ScriptedClient:
    """Pops one scripted reply per call; `default` answers once the script runs out."""

    def __init__(self, replies: list[SimpleNamespace], default: SimpleNamespace | None = None):
        self.replies = list(replies)
        self.default = default
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self.replies:
            return self.replies.pop(0)
        if self.default is not None:
            return self.default
        raise AssertionError("ScriptedClient ran out of replies")
