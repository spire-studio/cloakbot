from __future__ import annotations

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.hooks.context import Intent
from cloakbot.privacy.runtime.registry import get_worker

_SUPPORTED_INTENTS = {Intent.CHAT, Intent.MATH, Intent.DOC}


def normalize_intent(intent: Intent) -> Intent:
    if intent in _SUPPORTED_INTENTS:
        return intent
    return Intent.CHAT


def select_worker(intent: Intent) -> BaseAgent:
    return get_worker(normalize_intent(intent))
