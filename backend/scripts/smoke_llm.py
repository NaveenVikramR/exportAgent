"""One live call per Nemotron tier through the router.

Usage (from backend/):  python -m scripts.smoke_llm [--reasoning on|off|default]
"""

import argparse
import sys

from app.llm.router import LLMError, get_router
from app.llm.tasks import TaskType

# One representative task per tier in the default routing table.
TASKS = [TaskType.CLASSIFY, TaskType.DRAFT_REPLY, TaskType.RISK_REASONING]
MESSAGES = [
    {"role": "system", "content": "You are an assistant for an apparel export desk. Be brief."},
    {"role": "user", "content": "In one sentence, what does the Incoterm FOB mean?"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reasoning", choices=["on", "off", "default"], default="default")
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()
    reasoning = {"on": True, "off": False, "default": None}[args.reasoning]

    router = get_router()
    failures = 0
    total_cost = 0
    for task in TASKS:
        tier = router.tier_for(task)
        print(f"\n[{tier.value}] task={task.value}")
        try:
            result = router.complete(
                task, MESSAGES, max_tokens=args.max_tokens, reasoning=reasoning
            )
        except LLMError as exc:
            failures += 1
            print(f"  FAILED: {exc}")
            continue
        total_cost += result.cost_usd
        print(f"  model:         {result.model}")
        print(f"  tokens:        {result.input_tokens} in / {result.output_tokens} out")
        print(f"  latency:       {result.latency_ms} ms")
        print(f"  cost:          ${result.cost_usd}")
        print(f"  finish_reason: {result.finish_reason}")
        print(f"  reasoning:     {'returned' if result.reasoning else 'none returned'}")
        print(f"  content:       {(result.content or '<empty>').strip()}")
        print(f"  llm_calls.id:  {result.call_id}")

    print(f"\nTotal estimated cost: ${total_cost}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
