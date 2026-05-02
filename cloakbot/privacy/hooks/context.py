from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
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
    remote_prompt: str = ""
    remote_history_output: str = ""
    sanitized_input: str = ""
    sanitized_output: str = ""
    display_output: str = ""
    display_output_annotations: list[RestoredTokenAnnotation] = field(default_factory=list)
    local_computations: list[LocalComputationRecord] = field(default_factory=list)
    intent: Intent = Intent.CHAT
    user_input_entities: list[DetectedEntity] = field(default_factory=list)
    tool_input_entities: list[DetectedEntity] = field(default_factory=list)
    tool_output_entities: list[DetectedEntity] = field(default_factory=list)
    was_sanitized: bool = False
    tool_calls_made: int = 0
