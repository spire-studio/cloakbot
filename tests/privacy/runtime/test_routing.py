from cloakbot.privacy.agents.workers.chat_agent import ChatAgent
from cloakbot.privacy.agents.workers.math_agent import MathAgent
from cloakbot.privacy.hooks.context import Intent
from cloakbot.privacy.runtime.routing import normalize_intent, select_worker


def test_normalize_intent_keeps_supported_intents() -> None:
    assert normalize_intent(Intent.CHAT) is Intent.CHAT
    assert normalize_intent(Intent.MATH) is Intent.MATH


def test_select_worker_routes_chat_with_chat_worker_path() -> None:
    assert isinstance(select_worker(Intent.CHAT), ChatAgent)


def test_select_worker_routes_math_with_distinct_worker_path() -> None:
    assert isinstance(select_worker(Intent.MATH), MathAgent)
