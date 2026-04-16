from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from cloakbot.privacy.agents.intent_analyzer import (
    _INTENT_SYSTEM_PROMPT,
    UserIntentAnalyzer,
)
from cloakbot.privacy.hooks.context import Intent


@pytest.mark.asyncio
async def test_analyze_user_intent_returns_chat_for_plain_text() -> None:
    analyzer = UserIntentAnalyzer()
    analyzer._runner.complete = AsyncMock(
        return_value=(json.dumps({"intent": "chat"}), 1.0)
    )

    assert await analyzer.analyze("hello there") is Intent.CHAT


@pytest.mark.asyncio
async def test_analyze_user_intent_returns_math_for_numeric_scenario() -> None:
    analyzer = UserIntentAnalyzer()
    analyzer._runner.complete = AsyncMock(
        return_value=(json.dumps({"intent": "math"}), 1.0)
    )

    text = "What if Laurie gives me 10% of $100,000 instead of 20%?"
    assert await analyzer.analyze(text) is Intent.MATH


@pytest.mark.asyncio
async def test_analyze_user_intent_returns_doc_for_document_keywords() -> None:
    analyzer = UserIntentAnalyzer()
    analyzer._runner.complete = AsyncMock(
        return_value=(json.dumps({"intent": "doc"}), 1.0)
    )

    text = "Please summarize the attached PDF document"
    assert await analyzer.analyze(text) is Intent.DOC


@pytest.mark.asyncio
async def test_analyze_user_intent_falls_back_to_chat_on_invalid_json() -> None:
    analyzer = UserIntentAnalyzer()
    analyzer._runner.complete = AsyncMock(return_value=("not-json", 1.0))

    assert await analyzer.analyze("anything") is Intent.CHAT


def test_intent_prompt_prioritizes_math_for_mixed_intent() -> None:
    assert 'choose "math"' in _INTENT_SYSTEM_PROMPT.lower()
    assert "both explanation/chat and a concrete numeric calculation task" in _INTENT_SYSTEM_PROMPT
    assert "Information restatement is NOT computation" in _INTENT_SYSTEM_PROMPT
