from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cloakbot.privacy.core.types import DetectedEntity


class Intent(str, Enum):
    CHAT = "chat"
    MATH = "math"
    DOC = "doc"


@dataclass
class TurnContext:
    session_key: str
    turn_id: str
    raw_input: str
    sanitized_input: str = ""
    intent: Intent = Intent.CHAT
    user_input_entities: list[DetectedEntity] = field(default_factory=list)
    tool_input_entities: list[DetectedEntity] = field(default_factory=list)
    tool_output_entities: list[DetectedEntity] = field(default_factory=list)
    was_sanitized: bool = False
    tool_calls_made: int = 0
