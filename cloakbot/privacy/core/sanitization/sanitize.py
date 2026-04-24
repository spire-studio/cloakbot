"""Public privacy sanitization facade."""

from __future__ import annotations

from loguru import logger

from cloakbot.privacy.core.detection.detector import PiiDetector
from cloakbot.privacy.core.sanitization.handler import apply_tokens
from cloakbot.privacy.core.sanitization.restorer import (
    RestoredTokenAnnotation,
    restore_tokens,
    restore_tokens_with_annotations,
)
from cloakbot.privacy.core.state.vault import _SessionMap, get_map, save_map
from cloakbot.privacy.core.types import DetectedEntity, DetectionResult

_detector = PiiDetector()


async def _sanitize_with_detection(
    text: str,
    session_key: str,
    *,
    fail_open: bool,
    turn_id: str | None = None,
) -> tuple[str, bool, list[DetectedEntity], DetectionResult | None]:
    smap: _SessionMap = get_map(session_key)
    pre_swapped, pre_swapped_modified = smap.replace_known_originals(text)

    try:
        detection: DetectionResult = await _detector.detect(pre_swapped)
    except Exception:
        if fail_open:
            logger.warning(
                "sanitizer: local LLM unavailable — passing message through unsanitized "
                "(session={})",
                session_key,
            )
            return text, False, [], None
        raise

    logger.info(
        "sanitizer: detector entities for session {}: {}",
        session_key,
        [
            {
                "text": entity.text,
                "entity_type": entity.entity_type,
                **({"value": entity.value} if hasattr(entity, "value") else {}),
            }
            for entity in detection.sensitive_entities
        ],
    )

    sanitized, modified = apply_tokens(detection, smap, turn_id=turn_id)
    modified = modified or pre_swapped_modified

    logger.info(
        "sanitizer: tokenized input for session {}: {}",
        session_key,
        {
            "raw_input": text,
            "pre_swapped_input": pre_swapped,
            "sanitized_input": sanitized,
            "modified": modified,
        },
    )

    if modified:
        save_map(session_key, smap)

    return sanitized, modified, detection.sensitive_entities if modified else [], detection


async def sanitize_input(
    text: str,
    session_key: str,
    *,
    fail_open: bool = True,
    turn_id: str | None = None,
) -> tuple[str, bool, list[DetectedEntity]]:
    """Pass 1: detect and tokenize PII in user input."""
    sanitized, modified, entities, _detection = await sanitize_input_with_detection(
        text,
        session_key,
        fail_open=fail_open,
        turn_id=turn_id,
    )
    return sanitized, modified, entities


async def sanitize_input_with_detection(
    text: str,
    session_key: str,
    *,
    fail_open: bool = True,
    turn_id: str | None = None,
) -> tuple[str, bool, list[DetectedEntity], DetectionResult | None]:
    return await _sanitize_with_detection(
        text,
        session_key,
        fail_open=fail_open,
        turn_id=turn_id,
    )



async def sanitize_tool_output(
    text: str,
    session_key: str,
    *,
    turn_id: str | None = None,
) -> tuple[str, bool, list[DetectedEntity]]:
    """Pass 3: detect PII injected by tool call results."""
    sanitized, modified, entities, _detection = await _sanitize_with_detection(
        text,
        session_key,
        fail_open=False,
        turn_id=turn_id,
    )
    return sanitized, modified, entities


async def remap_response(text: str, session_key: str) -> str:
    """Restore all tokens in text back to original values using session vault."""
    smap: _SessionMap = get_map(session_key)
    return restore_tokens(text, smap)


async def remap_response_with_annotations(
    text: str,
    session_key: str,
) -> tuple[str, list[RestoredTokenAnnotation]]:
    """Restore all tokens and return metadata for the visible restored spans."""
    smap: _SessionMap = get_map(session_key)
    return restore_tokens_with_annotations(text, smap)
