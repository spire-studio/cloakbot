"""
Quick smoke test for the sanitizer pipeline.

Usage (from project root):
    cp .env.example .env   # fill in VLLM_BASE_URL and VLLM_API_KEY
    uv run python scripts/test_sanitizer.py
"""

import asyncio
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parents[1]))

from cloakbot.sanitizer import remap_response, sanitize_input
from cloakbot.providers.vllm import get_vllm_model, _settings

TEST_CASES = [
    {
        "label": "Personal PII",
        "text": "Hi, my name is Alice Chen and you can reach me at alice@acme.com or 138-0000-1234.",
    },
    {
        "label": "Business sensitive",
        "text": "We're acquiring TargetCorp for $205 million, closing December 15.",
    },
    {
        "label": "Clean input (should pass through)",
        "text": "What is the capital of France?",
    },
]

SESSION = "test:smoke"


async def main() -> None:
    print("=" * 60)
    print("CloakBot sanitizer smoke test")
    print("=" * 60)
    settings = _settings()
    print(f"vLLM base URL: {settings.base_url}")
    print(f"vLLM model   : {get_vllm_model()}")
    print(f"vLLM API key : {'set' if settings.api_key else 'missing'}")

    for case in TEST_CASES:
        print(f"\n[{case['label']}]")
        print(f"  Input    : {case['text']}")

        sanitized, modified, entities = await sanitize_input(case["text"], SESSION, fail_open=False)
        print(f"  Sanitized: {sanitized}")
        print(f"  Modified : {modified}")

        if modified:
            # Simulate an LLM response that echoes placeholders back
            fake_response = f"Got it. I'll keep {sanitized.split('{{')[1].split('}}')[0] if '{{' in sanitized else 'your info'} in mind."  # noqa
            # Actually just use the sanitized text as a fake response
            fake_response = sanitized
            restored = await remap_response(fake_response, SESSION)
            print(f"  Restored : {restored}")

    print("\n" + "=" * 60)
    print("Done. Check ~/.cloakbot/sanitizer_maps/ for session JSON.")


if __name__ == "__main__":
    asyncio.run(main())
