from __future__ import annotations

from typing import Literal

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.settings import ModelSettings

from cloakbot.privacy.core.detection.detector_model import build_detector_model
from cloakbot.privacy.hooks.context import Intent

_INTENT_SYSTEM_PROMPT = """You are an intent classifier for a privacy pipeline.

Classify the user's message into exactly one intent:
- chat: normal conversation, Q&A, planning, coding, or explanations without core numeric computation tasks.
- math: asks to compute, compare, forecast, or evaluate numeric scenarios.

Priority rules:
1. If the message includes both explanation/chat and a concrete numeric calculation task, choose "math".
2. If the message asks to process an attachment/document and also asks for calculations on that document, choose "math".
3. Choose "chat" for document, file, attachment, and dataset processing without explicit numeric computation. Document privacy is enforced at the tool-output boundary, not by a separate document intent.
4. Information restatement is NOT computation. Example: "What is his monthly salary?" when the value is already present -> "chat".
5. Use "math" only when an actual arithmetic operation or quantitative comparison is requested.

Return ONLY valid JSON:
{
  "intent": "<chat|math>"
}
"""


class IntentDecision(BaseModel):
    """Structured output target for the intent classifier LLM call."""

    intent: Literal["chat", "math"]


_INTENT_AGENT = Agent(
    output_type=NativeOutput(IntentDecision),
    instructions=_INTENT_SYSTEM_PROMPT,
    retries=1,
)


class UserIntentAnalyzer:
    """Analyze turn intent using the local model."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._temperature = temperature

    async def analyze(self, text: str) -> Intent:
        try:
            result = await _INTENT_AGENT.run(
                text,
                model=build_detector_model(),
                model_settings=ModelSettings(temperature=self._temperature),
            )
        except Exception:
            # Any failure — local model unavailable, or an unparseable / out-of-enum
            # response that survives the retry budget — is fail-safe to chat. The
            # restrictive `math` path must never be entered on a guess.
            logger.warning("IntentAnalyzer: classification unavailable, fallback to chat")
            return Intent.CHAT
        return Intent(result.output.intent)


_ANALYZER = UserIntentAnalyzer()


async def analyze_user_intent(text: str) -> Intent:
    """Return the pre-routing turn intent inferred from raw user text."""
    return await _ANALYZER.analyze(text)
