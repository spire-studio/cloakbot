from __future__ import annotations

from loguru import logger

from cloakbot.privacy.core.detection.llm_json import JsonCompletionRunner, load_json_object
from cloakbot.privacy.hooks.context import Intent

_INTENT_SYSTEM_PROMPT = """You are an intent classifier for a privacy pipeline.

Classify the user's message into exactly one intent:
- chat: normal conversation, Q&A, planning, coding, or explanations without core numeric computation tasks.
- math: asks to compute, compare, forecast, or evaluate numeric scenarios.
- doc: asks to process document/file/attachment content.

Priority rules:
1. If the message includes both explanation/chat and a concrete numeric calculation task, choose "math".
2. If the message asks to process an attachment/document and also asks for calculations on that document, choose "math".
3. Choose "doc" only when the core task is document processing without explicit numeric computation.
4. Choose "chat" only when neither math nor doc applies.
5. Information restatement is NOT computation. Example: "What is his monthly salary?" when the value is already present -> "chat".
6. Use "math" only when an actual arithmetic operation or quantitative comparison is requested.

Return ONLY valid JSON:
{
  "intent": "<chat|math|doc>"
}
"""


class UserIntentAnalyzer:
    """Analyze turn intent using the local model."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._runner = JsonCompletionRunner(temperature=temperature)

    async def analyze(self, text: str) -> Intent:
        try:
            raw_output, _latency_ms = await self._runner.complete(_INTENT_SYSTEM_PROMPT, text)
        except Exception:
            logger.warning("IntentAnalyzer: local model unavailable, fallback to chat")
            return Intent.CHAT
        data = load_json_object(raw_output)
        if not data:
            logger.warning("IntentAnalyzer: empty/invalid response, fallback to chat")
            return Intent.CHAT

        raw_intent = str(data.get("intent", "")).strip().lower()
        if raw_intent == Intent.MATH.value:
            return Intent.MATH
        if raw_intent == Intent.DOC.value:
            return Intent.DOC
        if raw_intent == Intent.CHAT.value:
            return Intent.CHAT

        logger.warning("IntentAnalyzer: unknown intent '{}', fallback to chat", raw_intent)
        return Intent.CHAT


_ANALYZER = UserIntentAnalyzer()


async def analyze_user_intent(text: str) -> Intent:
    """Return the pre-routing turn intent inferred from raw user text."""
    return await _ANALYZER.analyze(text)
