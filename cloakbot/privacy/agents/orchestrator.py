from __future__ import annotations

import uuid

from loguru import logger

from cloakbot.privacy.agents.intent_analyzer import analyze_user_intent
from cloakbot.privacy.agents.task_router import get_agent, route_turn
from cloakbot.privacy.core.sanitize import (
    remap_response_with_annotations,
    sanitize_input_with_detection,
)
from cloakbot.privacy.core.restorer import build_local_computation_annotations
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.transparency.report import TurnReport


class PrivacyOrchestrator:
    """Coordinate the per-turn privacy pipeline around the remote LLM call."""

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
        sanitized, modified, entities, _detection = await sanitize_input_with_detection(
            text,
            session_key,
            fail_open=fail_open,
            turn_id=ctx.turn_id,
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

        agent = get_agent(ctx)
        prepared = await agent.prepare_input(ctx)
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
        agent = get_agent(ctx)
        finalized = await agent.finalize_output(response, ctx)
        ctx.sanitized_output = finalized

        restored, annotations = await remap_response_with_annotations(finalized, ctx.session_key)
        annotations.extend(build_local_computation_annotations(restored, ctx.local_computations))
        annotations.sort(key=lambda annotation: (annotation.start, annotation.end))
        ctx.display_output = restored
        ctx.display_output_annotations = annotations

        report_text = TurnReport(ctx=ctx).render()
        if include_report and report_text:
            restored = f"{restored}\n\n{report_text}"
        return restored


_ORCHESTRATOR = PrivacyOrchestrator()


def get_orchestrator() -> PrivacyOrchestrator:
    """Return the process-wide privacy orchestrator instance."""
    return _ORCHESTRATOR
