from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import DetectedEntity
from cloakbot.privacy.document_redaction import UserDocumentResult
from cloakbot.privacy.tool_models import ToolApprovalRequest, ToolPrivacyRecord, ToolVaultArtifact
from cloakbot.privacy.visual_redaction import VisualPrivacyRedaction


class Intent(str, Enum):
    CHAT = "chat"
    MATH = "math"


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
    tool_results: list[ToolPrivacyRecord] = field(default_factory=list)
    tool_approvals: list[ToolApprovalRequest] = field(default_factory=list)
    # Visual privacy state from the user's *initial* prompt (image attachments).
    # Kept separate from ``tool_results`` so the report can distinguish "user
    # uploaded a redacted invoice" from "a tool returned a redacted image."
    user_input_visual_redactions: list[VisualPrivacyRedaction] = field(default_factory=list)
    user_input_vault_artifacts: list[ToolVaultArtifact] = field(default_factory=list)
    user_input_media_blocks: list[dict[str, Any]] = field(default_factory=list)
    # User-uploaded text documents (.txt / .md) routed through the
    # chunker-backed PII detector. Sibling field to the visual ones —
    # the WebUI privacy payload emits both so the Local-vs-Remote
    # toggle can flip text uploads the same way it flips image uploads.
    user_input_documents: list[UserDocumentResult] = field(default_factory=list)
    user_input_document_artifacts: list[ToolVaultArtifact] = field(default_factory=list)
    was_sanitized: bool = False
    tool_calls_made: int = 0
