from __future__ import annotations

from cloakbot.privacy.agents.workers.chat_agent import ChatAgent
from cloakbot.privacy.agents.workers.math_agent import MathAgent
from cloakbot.privacy.agents.runtime.task_router import get_agent, route_turn
from cloakbot.privacy.hooks.context import Intent, TurnContext


def test_route_turn_returns_math_when_intent_is_math() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="what is 3 + 2?",
        intent=Intent.MATH,
    )

    assert route_turn(ctx) is Intent.MATH


def test_route_turn_returns_chat_by_default() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="hello",
    )

    assert route_turn(ctx) is Intent.CHAT


def test_get_agent_returns_math_agent_for_math_turn() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="what is 3 + 2?",
        intent=Intent.MATH,
    )

    assert isinstance(get_agent(ctx), MathAgent)


def test_get_agent_returns_chat_agent_for_chat_turn() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="hello",
        intent=Intent.CHAT,
    )

    assert isinstance(get_agent(ctx), ChatAgent)


def test_route_turn_preserves_doc_intent() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="summarize this document",
        intent=Intent.DOC,
    )

    assert route_turn(ctx) is Intent.DOC
