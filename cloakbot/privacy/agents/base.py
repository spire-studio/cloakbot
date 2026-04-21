from __future__ import annotations

from abc import ABC, abstractmethod

from cloakbot.privacy.hooks.context import TurnContext


class BaseAgent(ABC):
    """Base interface for privacy task agents."""

    @abstractmethod
    async def prepare_input(self, ctx: TurnContext) -> str:
        """Prepare sanitized user content before the remote LLM call."""

    @abstractmethod
    async def finalize_output(self, response: str, ctx: TurnContext) -> str:
        """Apply local post-processing after the remote LLM response arrives."""
