"""Public privacy sanitization facade."""

from __future__ import annotations

from loguru import logger

from cloakbot.privacy.core.detection.chunking import ContentType
from cloakbot.privacy.core.detection.detector import PiiDetector
from cloakbot.privacy.core.detection.general_detector import scan_partial_candidates
from cloakbot.privacy.core.detection.tool_detector import (
    ToolDetectionContext,
    ToolPrivacyDetector,
)
from cloakbot.privacy.core.sanitization.handler import apply_tokens
from cloakbot.privacy.core.sanitization.restorer import (
    RestoredTokenAnnotation,
    restore_tokens,
    restore_tokens_with_annotations,
)
from cloakbot.privacy.core.state.vault import _SessionMap, get_map, save_map
from cloakbot.privacy.core.types import DetectedEntity, DetectionResult

_detector = PiiDetector()
_tool_detector_singleton: ToolPrivacyDetector | None = None
_ALIAS_PRONE_ENTITY_TYPES = {"person", "org"}


def _tool_detector() -> ToolPrivacyDetector:
    """Lazy-instantiated tool detector so module import stays cheap."""
    global _tool_detector_singleton
    if _tool_detector_singleton is None:
        _tool_detector_singleton = ToolPrivacyDetector(detector=_detector)
    return _tool_detector_singleton


def _alias_prone_vault_entries(smap: _SessionMap) -> list[dict[str, str]]:
    return [
        {"canonical": entity.canonical, "type": entity.entity_type}
        for entity in smap.placeholder_to_entity.values()
        if entity.entity_type in _ALIAS_PRONE_ENTITY_TYPES and entity.canonical
    ]


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
        detection: DetectionResult = await _detector.detect(
            pre_swapped,
            partial_candidates=scan_partial_candidates(
                pre_swapped,
                _alias_prone_vault_entries(smap),
            ),
        )
    except Exception:
        if fail_open:
            logger.warning(
                "sanitizer: local LLM unavailable — passing message through unsanitized "
                "(session={})",
                session_key,
            )
            return text, False, [], None
        raise

    # Telemetry hygiene: log entity counts/types only, never values.
    # A privacy log line that contains the very PII it was redacting is
    # itself a privacy leak (and a frequent forensics finding).
    logger.info(
        "sanitizer: detector summary for session {}: {} entities, types={}",
        session_key,
        len(detection.sensitive_entities),
        sorted({entity.entity_type for entity in detection.sensitive_entities}),
    )

    sanitized, modified = apply_tokens(detection, smap, turn_id=turn_id)
    modified = modified or pre_swapped_modified

    logger.debug(
        "sanitizer: tokenized input for session {}: modified={} raw_len={} sanitized_len={}",
        session_key,
        modified,
        len(text),
        len(sanitized),
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


async def sanitize_tool_output_chunked(
    text: str,
    session_key: str,
    *,
    tool_name: str,
    turn_id: str | None = None,
    content_type: ContentType | None = None,
) -> tuple[str, bool, list[DetectedEntity], bool]:
    """Detect + tokenize tool output via the chunked tool detector.

    Returns ``(sanitized, modified, entities, chunks_failed)``. The
    extra fourth element signals "at least one chunk's local detection
    failed (timeout / exception / malformed model output)" — the caller
    is expected to treat this as a fail-closed condition (replace the
    payload with an omit placeholder) because we may have missed PII.

    Pre-swaps known originals via the session vault before chunking, so
    values already mapped from earlier turns reuse the same placeholder
    instead of producing a fresh one.
    """
    smap: _SessionMap = get_map(session_key)
    pre_swapped, pre_swapped_modified = smap.replace_known_originals(text)

    result = await _tool_detector().detect(
        pre_swapped,
        ToolDetectionContext(
            tool_name=tool_name,
            session_key=session_key,
            turn_id=turn_id or "",
            content_type=content_type,
        ),
    )

    detection = DetectionResult(
        original_prompt=pre_swapped,
        entities=result.entities,
        llm_raw_output="",
        latency_ms=0.0,
    )
    sanitized, modified = apply_tokens(detection, smap, turn_id=turn_id)
    modified = modified or pre_swapped_modified

    if modified:
        save_map(session_key, smap)

    logger.info(
        "tool sanitizer: tool={} chunks={} failed={} entities={} types={}",
        tool_name,
        result.chunks_total,
        result.chunks_failed,
        len(result.entities),
        sorted({e.entity_type for e in result.entities}),
    )

    return (
        sanitized,
        modified,
        result.entities if modified else [],
        result.has_failures,
    )


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
