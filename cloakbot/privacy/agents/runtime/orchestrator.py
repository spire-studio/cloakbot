from __future__ import annotations

import uuid

from loguru import logger

from cloakbot.privacy.agents.classification.intent_analyzer import analyze_user_intent
from cloakbot.privacy.agents.runtime.task_router import get_agent, route_turn
from cloakbot.privacy.core.sanitization.sanitize import (
    remap_response_with_annotations,
    sanitize_input_with_detection,
)
from cloakbot.privacy.core.sanitization.restorer import build_local_computation_annotations
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import emit_event
from cloakbot.privacy.transparency.report import TurnReport


class PrivacyOrchestrator:
    """Coordinate the per-turn privacy pipeline around the remote LLM call."""

    @staticmethod
    def _trace_id(ctx: TurnContext) -> str:
        return f"{ctx.session_key}:{ctx.turn_id}"

    @staticmethod
    def _span_id(ctx: TurnContext, stage: str) -> str:
        return f"{ctx.turn_id}:{stage}"

    async def prepare_turn(
        self,
        text: str,
        session_key: str,
        *,
        fail_open: bool = True,
    ) -> tuple[str, TurnContext]:
        """Run pass 1 and prepare sanitized content for the remote LLM."""
        ctx = TurnContext(
            session_key=session_key,
            turn_id=str(uuid.uuid4()),
            raw_input=text,
        )
        trace_id = self._trace_id(ctx)
        emit_event(
            event_type=EventType.TURN_RECEIVED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "received"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.RAW,
            status=ProtocolStatus.STARTED,
            payload={"intent": ctx.intent.value},
        )
        emit_event(
            event_type=EventType.TURN_SANITIZE_STARTED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "sanitize"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.RAW,
            status=ProtocolStatus.STARTED,
            payload={"input_length": len(text)},
        )
        try:
            sanitized, modified, entities, _detection = await sanitize_input_with_detection(
                text,
                session_key,
                fail_open=fail_open,
                turn_id=ctx.turn_id,
            )
        except Exception as exc:
            emit_event(
                event_type=EventType.TURN_SANITIZE_FAILED,
                trace_id=trace_id,
                span_id=self._span_id(ctx, "sanitize"),
                session_id=ctx.session_key,
                turn_id=ctx.turn_id,
                stage=PrivacyStage.RAW,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc)},
            )
            raise

        emit_event(
            event_type=EventType.TURN_SANITIZE_SUCCEEDED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "sanitize"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"was_sanitized": modified},
        )
        ctx.sanitized_input = sanitized
        ctx.was_sanitized = modified
        ctx.user_input_entities = entities
        logger.info(
            "privacy-orchestrator: turn context prepared for session {}: {}",
            session_key,
            {
                "turn_id": ctx.turn_id,
                "sanitized_input": ctx.sanitized_input,
                "user_input_entities": [
                    {
                        "text": entity.text,
                        "entity_type": entity.entity_type,
                        **({"value": entity.value} if hasattr(entity, "value") else {}),
                    }
                    for entity in ctx.user_input_entities
                ],
                "was_sanitized": ctx.was_sanitized,
            },
        )
        ctx.intent = await analyze_user_intent(text)
        ctx.intent = route_turn(ctx)

        emit_event(
            event_type=EventType.TURN_DISPATCH_STARTED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "dispatch"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.STARTED,
            payload={"intent": ctx.intent.value},
        )

        agent = get_agent(ctx)
        try:
            prepared = await agent.prepare_input(ctx)
        except Exception as exc:
            emit_event(
                event_type=EventType.TURN_DISPATCH_FAILED,
                trace_id=trace_id,
                span_id=self._span_id(ctx, "dispatch"),
                session_id=ctx.session_key,
                turn_id=ctx.turn_id,
                stage=PrivacyStage.SANITIZED,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc), "intent": ctx.intent.value},
            )
            raise

        emit_event(
            event_type=EventType.TURN_DISPATCH_COMPLETED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "dispatch"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"intent": ctx.intent.value},
        )
        ctx.remote_prompt = prepared
        return prepared, ctx

    async def finalize_turn(
        self,
        response: str,
        ctx: TurnContext,
        *,
        include_report: bool = True,
    ) -> str:
        """Run local post-processing, restore tokens and emit report."""
        trace_id = self._trace_id(ctx)
        emit_event(
            event_type=EventType.TURN_RESTORE_STARTED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "restore"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.STARTED,
            payload={"response_length": len(response)},
        )

        agent = get_agent(ctx)
        try:
            finalized = await agent.finalize_output(response, ctx)
            ctx.sanitized_output = finalized

            restored, annotations = await remap_response_with_annotations(finalized, ctx.session_key)
            annotations.extend(build_local_computation_annotations(restored, ctx.local_computations))
            annotations.sort(key=lambda annotation: (annotation.start, annotation.end))
            ctx.display_output = restored
            ctx.display_output_annotations = annotations
        except Exception as exc:
            emit_event(
                event_type=EventType.TURN_RESTORE_FAILED,
                trace_id=trace_id,
                span_id=self._span_id(ctx, "restore"),
                session_id=ctx.session_key,
                turn_id=ctx.turn_id,
                stage=PrivacyStage.SANITIZED,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc)},
            )
            raise

        emit_event(
            event_type=EventType.TURN_RESTORE_COMPLETED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "restore"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.POSTPROCESSED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"annotation_count": len(annotations)},
        )

        report_text = TurnReport(ctx=ctx).render()
        if include_report and report_text:
            restored = f"{restored}\n\n{report_text}"

        emit_event(
            event_type=EventType.TURN_COMPLETED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "completed"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.POSTPROCESSED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"include_report": include_report},
        )
        return restored


_ORCHESTRATOR = PrivacyOrchestrator()


def get_orchestrator() -> PrivacyOrchestrator:
    """Return the process-wide privacy orchestrator instance."""
    return _ORCHESTRATOR
