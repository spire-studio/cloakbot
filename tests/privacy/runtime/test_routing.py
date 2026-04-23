from cloakbot.privacy.agents.workers.chat_agent import ChatAgent
from cloakbot.privacy.agents.workers.math_agent import MathAgent
from cloakbot.privacy.hooks.context import Intent
from cloakbot.privacy.runtime.registry import get_worker
from cloakbot.privacy.runtime.routing import normalize_intent


def test_normalize_intent_keeps_supported_intents() -> None:
    assert normalize_intent(Intent.CHAT) is Intent.CHAT
    assert normalize_intent(Intent.MATH) is Intent.MATH
    assert normalize_intent(Intent.DOC) is Intent.DOC


def test_get_worker_routes_doc_with_chat_worker_path() -> None:
    assert isinstance(get_worker(Intent.DOC), ChatAgent)


def test_get_worker_routes_math_with_distinct_worker_path() -> None:
    assert isinstance(get_worker(Intent.MATH), MathAgent)
