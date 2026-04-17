"""Public privacy sanitization facade."""

from __future__ import annotations

from loguru import logger

from cloakbot.privacy.core.detector import PiiDetector
from cloakbot.privacy.core.types import DetectedEntity, DetectionResult
from cloakbot.privacy.core.handler import apply_tokens
from cloakbot.privacy.core.restorer import restore_tokens
from cloakbot.privacy.core.vault import _SessionMap, get_map, save_map

_detector = PiiDetector()


async def _sanitize_with_detection(
    text: str,
    session_key: str,
    *,
    fail_open: bool,
) -> tuple[str, bool, list[DetectedEntity], DetectionResult | None]:
    try:
        detection: DetectionResult = await _detector.detect(text)
    except Exception:
        if fail_open:
            logger.warning(
                "sanitizer: local LLM unavailable — passing message through unsanitized "
                "(session={})",
                session_key,
            )
            return text, False, [], None
        raise

    smap: _SessionMap = get_map(session_key)
    sanitized, modified = apply_tokens(detection, smap)

    if modified:
        save_map(session_key, smap)

    return sanitized, modified, detection.sensitive_entities if modified else [], detection


async def sanitize_input(
    text: str,
    session_key: str,
    *,
    fail_open: bool = True,
) -> tuple[str, bool, list[DetectedEntity]]:
    """Pass 1: detect and tokenize PII in user input."""
    sanitized, modified, entities, _detection = await sanitize_input_with_detection(
        text,
        session_key,
        fail_open=fail_open,
    )
    return sanitized, modified, entities


async def sanitize_input_with_detection(
    text: str,
    session_key: str,
    *,
    fail_open: bool = True,
) -> tuple[str, bool, list[DetectedEntity], DetectionResult | None]:
    return await _sanitize_with_detection(
        text,
        session_key,
        fail_open=fail_open,
    )



async def sanitize_tool_output(
    text: str,
    session_key: str,
) -> tuple[str, bool, list[DetectedEntity]]:
    """Pass 3: detect PII injected by tool call results."""
    sanitized, modified, entities, _detection = await _sanitize_with_detection(
        text,
        session_key,
        fail_open=False,
    )
    return sanitized, modified, entities


async def remap_response(text: str, session_key: str) -> str:
    """Restore all tokens in text back to original values using session vault."""
    smap: _SessionMap = get_map(session_key)
    return restore_tokens(text, smap)
