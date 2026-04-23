from __future__ import annotations

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.agents.workers.chat_agent import ChatAgent
from cloakbot.privacy.agents.workers.math_agent import MathAgent
from cloakbot.privacy.hooks.context import Intent

_WORKERS: dict[Intent, BaseAgent] = {
    Intent.CHAT: ChatAgent(),
    Intent.MATH: MathAgent(),
    Intent.DOC: ChatAgent(),
}


def get_worker(intent: Intent) -> BaseAgent:
    return _WORKERS[intent]
