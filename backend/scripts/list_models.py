"""List the model IDs Token Factory serves for this API key.

Usage (from backend/):  python -m scripts.list_models [--all]
By default only NVIDIA models are shown.
"""

import argparse
import sys

from openai import OpenAIError

from app.config import get_settings
from app.llm.router import LLMError, get_router


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="show every model, not just NVIDIA")
    args = parser.parse_args()

    settings = get_settings()
    try:
        models = get_router().client.models.list(extra_query={"verbose": "true"})
    except (LLMError, OpenAIError) as exc:
        print(f"FAILED: {exc}")
        return 1

    configured = {
        settings.nebius_model_nano: "NANO",
        settings.nebius_model_super: "SUPER",
        settings.nebius_model_ultra: "ULTRA",
    }
    served = set()
    for model in sorted(models, key=lambda m: m.id.lower()):
        served.add(model.id)
        if not args.all and "nvidia" not in model.id.lower() and "nemotron" not in model.id.lower():
            continue
        pricing = (model.model_extra or {}).get("pricing") or {}
        price = (
            f"  prompt={pricing.get('prompt')} completion={pricing.get('completion')} (USD/token)"
            if pricing
            else ""
        )
        tag = f"  <- NEBIUS_MODEL_{configured[model.id]}" if model.id in configured else ""
        print(f"{model.id}{price}{tag}")

    missing = [f"NEBIUS_MODEL_{tier}={model_id}" for model_id, tier in configured.items() if model_id not in served]
    if missing:
        print("\nConfigured but NOT served (fix these in .env):")
        for line in missing:
            print(f"  {line}")
        return 1
    print("\nAll three configured tier models are served.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
