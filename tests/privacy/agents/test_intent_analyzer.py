from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from cloakbot.privacy.agents.classification.intent_analyzer import (
    _INTENT_SYSTEM_PROMPT,
    UserIntentAnalyzer,
)
from cloakbot.privacy.hooks.context import Intent

_TARGET = "cloakbot.privacy.agents.classification.intent_analyzer.build_detector_model"


def _fixed_model(payload: str) -> FunctionModel:
    return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(payload)]))


@pytest.mark.asyncio
async def test_analyze_user_intent_returns_chat_for_plain_text() -> None:
    with patch(_TARGET, return_value=_fixed_model(json.dumps({"intent": "chat"}))):
        assert await UserIntentAnalyzer().analyze("hello there") is Intent.CHAT


@pytest.mark.asyncio
async def test_analyze_user_intent_returns_math_for_numeric_scenario() -> None:
    text = "What if Laurie gives me 10% of $100,000 instead of 20%?"
    with patch(_TARGET, return_value=_fixed_model(json.dumps({"intent": "math"}))):
        assert await UserIntentAnalyzer().analyze(text) is Intent.MATH


@pytest.mark.asyncio
async def test_analyze_user_intent_falls_back_to_chat_for_out_of_enum_intent() -> None:
    # A legacy/unknown intent like "doc" is not in the chat|math schema, so it
    # fails validation, exhausts the retry budget, and falls back to chat.
    text = "Please summarize the attached PDF document"
    with patch(_TARGET, return_value=_fixed_model(json.dumps({"intent": "doc"}))):
        assert await UserIntentAnalyzer().analyze(text) is Intent.CHAT


@pytest.mark.asyncio
async def test_analyze_user_intent_falls_back_to_chat_on_invalid_json() -> None:
    with patch(_TARGET, return_value=_fixed_model("not-json")):
        assert await UserIntentAnalyzer().analyze("anything") is Intent.CHAT


@pytest.mark.asyncio
async def test_analyze_user_intent_falls_back_to_chat_when_local_model_unavailable() -> None:
    with patch(_TARGET, side_effect=RuntimeError("missing vllm config")):
        assert await UserIntentAnalyzer().analyze("anything") is Intent.CHAT


def test_intent_prompt_prioritizes_math_for_mixed_intent() -> None:
    assert 'choose "math"' in _INTENT_SYSTEM_PROMPT.lower()
    assert "both explanation/chat and a concrete numeric calculation task" in _INTENT_SYSTEM_PROMPT
    assert "Document privacy is enforced at the tool-output boundary" in _INTENT_SYSTEM_PROMPT
    assert "Information restatement is NOT computation" in _INTENT_SYSTEM_PROMPT
