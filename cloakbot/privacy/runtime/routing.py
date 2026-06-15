from __future__ import annotations

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.agents.workers.chat_agent import ChatAgent
from cloakbot.privacy.agents.workers.math_agent import MathAgent
from cloakbot.privacy.hooks.context import Intent

# The intent → worker table is the single source of truth for which intents are
# supported; ``normalize_intent`` derives the supported set from its keys.
_WORKERS: dict[Intent, BaseAgent] = {
    Intent.CHAT: ChatAgent(),
    Intent.MATH: MathAgent(),
}


def normalize_intent(intent: Intent) -> Intent:
    """Map any unsupported intent onto the default ``CHAT`` worker."""
    return intent if intent in _WORKERS else Intent.CHAT


def select_worker(intent: Intent) -> BaseAgent:
    """Return the worker for *intent*, normalizing unsupported intents to chat."""
    return _WORKERS[normalize_intent(intent)]
