from __future__ import annotations

import re

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.hooks.context import TurnContext

_LOCAL_PATH_PLACEHOLDER_RE = re.compile(r"<<LOCAL_PATH_\d+>>")
_LOCAL_PATH_TOOL_INSTRUCTION = (
    "[Local file access required]\n"
    "If the user asks about any <<LOCAL_PATH_N>> reference, call read_file with that placeholder first.\n"
    "Do not ask the user to upload, paste, or re-send the file when a <<LOCAL_PATH_N>> is already present."
)


class ChatAgent(BaseAgent):
    """Default privacy agent for standard chat turns."""

    async def prepare_input(self, ctx: TurnContext) -> str:
        if _LOCAL_PATH_PLACEHOLDER_RE.search(ctx.sanitized_input):
            return f"{ctx.sanitized_input}\n\n{_LOCAL_PATH_TOOL_INSTRUCTION}"
        return ctx.sanitized_input

    async def finalize_output(self, response: str, ctx: TurnContext) -> str:
        return response
