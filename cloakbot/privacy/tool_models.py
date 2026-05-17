from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.types import DetectedEntity
from cloakbot.privacy.visual_redaction import VisualPrivacyRedaction
from cloakbot.tool_privacy import ToolPrivacyClass

if TYPE_CHECKING:
    from cloakbot.privacy.hooks.context import TurnContext


class ToolApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ToolPrivacyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ToolVaultArtifact(ToolPrivacyModel):
    kind: str
    path: str
    media_type: str | None = Field(default=None, alias="mediaType")


class ToolPrivacyRecord(ToolPrivacyModel):
    tool_call_id: str
    tool_name: str
    privacy_class: ToolPrivacyClass = ToolPrivacyClass.LOCAL
    remote_arguments: dict[str, Any]
    sanitized_output: str
    was_sanitized: bool
    visual_redactions: list[VisualPrivacyRedaction] = Field(default_factory=list)
    vault_artifacts: list[ToolVaultArtifact] = Field(default_factory=list, alias="vaultArtifacts")


class ToolApprovalRequest(ToolPrivacyModel):
    approval_id: str
    session_key: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    privacy_class: ToolPrivacyClass
    remote_arguments: dict[str, Any]
    restored_arguments: dict[str, Any]
    detected_entities: list[DetectedEntity] = Field(default_factory=list)
    status: ToolApprovalStatus = ToolApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None

    def approved(self) -> "ToolApprovalRequest":
        return self.model_copy(
            update={
                "status": ToolApprovalStatus.APPROVED,
                "resolved_at": datetime.now(),
            }
        )

    def denied(self) -> "ToolApprovalRequest":
        return self.model_copy(
            update={
                "status": ToolApprovalStatus.DENIED,
                "resolved_at": datetime.now(),
            }
        )


class ToolTurnState(ToolPrivacyModel):
    session_key: str
    turn_id: str
    raw_input: str
    remote_prompt: str = ""
    sanitized_input: str = ""
    intent: str = "chat"
    user_input_entities: list[DetectedEntity] = Field(default_factory=list)
    tool_input_entities: list[DetectedEntity] = Field(default_factory=list)
    tool_output_entities: list[DetectedEntity] = Field(default_factory=list)
    tool_results: list[ToolPrivacyRecord] = Field(default_factory=list)
    tool_approvals: list[ToolApprovalRequest] = Field(default_factory=list)
    local_computations: list[LocalComputationRecord] = Field(default_factory=list)
    was_sanitized: bool = False
    tool_calls_made: int = 0

    @classmethod
    def from_context(cls, ctx: "TurnContext") -> "ToolTurnState":
        intent = getattr(ctx.intent, "value", ctx.intent)
        return cls(
            session_key=ctx.session_key,
            turn_id=ctx.turn_id,
            raw_input=ctx.raw_input,
            remote_prompt=ctx.remote_prompt,
            sanitized_input=ctx.sanitized_input,
            intent=str(intent),
            user_input_entities=ctx.user_input_entities,
            tool_input_entities=ctx.tool_input_entities,
            tool_output_entities=ctx.tool_output_entities,
            tool_results=ctx.tool_results,
            tool_approvals=ctx.tool_approvals,
            local_computations=ctx.local_computations,
            was_sanitized=ctx.was_sanitized,
            tool_calls_made=ctx.tool_calls_made,
        )

    def to_context(self) -> TurnContext:
        from cloakbot.privacy.hooks.context import Intent, TurnContext

        return TurnContext(
            session_key=self.session_key,
            turn_id=self.turn_id,
            raw_input=self.raw_input,
            remote_prompt=self.remote_prompt,
            sanitized_input=self.sanitized_input,
            intent=Intent(self.intent),
            user_input_entities=list(self.user_input_entities),
            tool_input_entities=list(self.tool_input_entities),
            tool_output_entities=list(self.tool_output_entities),
            tool_results=list(self.tool_results),
            tool_approvals=list(self.tool_approvals),
            local_computations=list(self.local_computations),
            was_sanitized=self.was_sanitized,
            tool_calls_made=self.tool_calls_made,
        )


class PendingToolApproval(ToolPrivacyModel):
    request: ToolApprovalRequest
    messages: list[dict[str, Any]]
    save_skip: int
    turn: ToolTurnState


class ToolApprovalRequiredError(RuntimeError):
    def __init__(self, request: ToolApprovalRequest) -> None:
        self.request = request
        super().__init__(f"Tool approval required for {request.tool_name}")
