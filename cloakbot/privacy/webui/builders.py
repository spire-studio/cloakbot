from __future__ import annotations

from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.replay import build_turn_timeline
from cloakbot.privacy.transparency.report import build_session_privacy_snapshot
from cloakbot.privacy.webui.contracts import (
    WebUIPrivacyPayload,
    WebUIPrivacyTimeline,
    WebUIPrivacyTimelineEvent,
    WebUIPrivacyTurn,
    WebUIToolApproval,
    WebUIToolResult,
)


def build_webui_privacy_turn(ctx: TurnContext) -> WebUIPrivacyTurn:
    return WebUIPrivacyTurn(
        turn_id=ctx.turn_id,
        intent=ctx.intent.value,
        remote_prompt=ctx.sanitized_input,
        local_computations=ctx.local_computations,
        tool_results=[
            WebUIToolResult(
                tool_call_id=result.tool_call_id,
                tool_name=result.tool_name,
                remote_arguments=result.remote_arguments,
                sanitized_output=result.sanitized_output,
                was_sanitized=result.was_sanitized,
                visual_redactions=result.visual_redactions,
            )
            for result in ctx.tool_results
        ],
        tool_approvals=[
            WebUIToolApproval(
                approval_id=approval.approval_id,
                tool_call_id=approval.tool_call_id,
                tool_name=approval.tool_name,
                privacy_class=approval.privacy_class,
                remote_arguments=approval.remote_arguments,
                restored_arguments=approval.restored_arguments,
                detected_entities=approval.detected_entities,
                status=approval.status,
            )
            for approval in ctx.tool_approvals
        ],
    )


def build_webui_privacy_timeline(session_key: str, ctx: TurnContext) -> WebUIPrivacyTimeline:
    timeline = build_turn_timeline(session_key, ctx.turn_id)
    return WebUIPrivacyTimeline(
        turn_id=ctx.turn_id,
        trace_id=timeline.trace_id,
        total_duration_ms=timeline.total_duration_ms,
        stage_durations_ms=timeline.stage_durations_ms,
        events=[
            WebUIPrivacyTimelineEvent(
                event_type=event.event_type.value,
                sequence=event.sequence,
                stage=event.stage.value,
                status=event.status.value,
                span_id=event.span_id,
                parent_span_id=event.parent_span_id,
                timestamp=event.timestamp,
                duration_ms=event.duration_ms,
                payload=event.payload,
            )
            for event in timeline.events
        ],
    )


def build_webui_privacy_payload(session_key: str, ctx: TurnContext) -> WebUIPrivacyPayload:
    return WebUIPrivacyPayload(
        privacy=build_session_privacy_snapshot(session_key),
        privacy_annotations=ctx.display_output_annotations,
        privacy_turn=build_webui_privacy_turn(ctx),
        privacy_timeline=build_webui_privacy_timeline(session_key, ctx),
    )
