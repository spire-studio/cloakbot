"""
Sanitizer — main entry point for the CloakBot privacy layer.

Two public coroutines:
  sanitize_input(text, session_key)   → (sanitized_text, was_modified)
  remap_response(text, session_key)   → restored_text

Session-level mapping
---------------------
Placeholder assignments are persisted per session as JSON at:
  ~/.nanobot/sanitizer_maps/<safe_session_key>.json

This means the same entity (e.g. "Alice") always maps to the same placeholder
(e.g. "{{PERSON_1}}") across all turns in a session, and placeholders that
appear in later LLM responses can still be remapped back.

Fail-open behaviour
-------------------
If the local vLLM server is unreachable, sanitize_input() logs a warning and
returns the original text unmodified rather than blocking the user.  The
caller in loop.py can change this policy by catching the exception explicitly.

Placeholder format: {{TAG_N}}  e.g. {{PERSON_1}}, {{EMAIL_2}}
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.sanitizer.pii_detector import ENTITY_TAG, DetectedEntity, DetectionResult, PiiDetector


# ---------------------------------------------------------------------------
# Session map — persisted as JSON
# ---------------------------------------------------------------------------

@dataclass
class _SessionMap:
    """In-memory view of a session's placeholder mapping table."""
    original_to_placeholder: dict[str, str]   # "Alice"      → "{{PERSON_1}}"
    placeholder_to_original: dict[str, str]   # "{{PERSON_1}}" → "Alice"
    counters: dict[str, int]                  # "PERSON" → 1  (highest index used)


def _safe_key(session_key: str) -> str:
    """Convert a session key like 'telegram:12345' to a safe filename stem."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_key)


def _map_path(session_key: str) -> Path:
    maps_dir = Path.home() / ".nanobot" / "sanitizer_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    return maps_dir / f"{_safe_key(session_key)}.json"


def _load_map(session_key: str) -> _SessionMap:
    path = _map_path(session_key)
    if path.exists():
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return _SessionMap(
                original_to_placeholder=data.get("original_to_placeholder", {}),
                placeholder_to_original=data.get("placeholder_to_original", {}),
                counters=data.get("counters", {}),
            )
        except Exception:
            logger.warning("sanitizer: corrupt session map at {}; resetting", path)
    return _SessionMap(
        original_to_placeholder={},
        placeholder_to_original={},
        counters={},
    )


def _save_map(session_key: str, smap: _SessionMap) -> None:
    path = _map_path(session_key)
    try:
        path.write_text(
            json.dumps(
                {
                    "original_to_placeholder": smap.original_to_placeholder,
                    "placeholder_to_original": smap.placeholder_to_original,
                    "counters": smap.counters,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("sanitizer: failed to save session map for {}", session_key)


# ---------------------------------------------------------------------------
# Rewrite (pure Python, no LLM)
# ---------------------------------------------------------------------------

def _rewrite(detection: DetectionResult, smap: _SessionMap) -> tuple[str, bool]:
    """
    Replace sensitive entities with placeholders, reusing existing assignments.

    Processes longest entities first to avoid partial-match collisions
    (e.g. replace "张伟明" before "张伟").

    Returns (rewritten_text, was_modified).
    """
    sensitive = detection.sensitive_entities
    if not sensitive:
        return detection.original_prompt, False

    ordered = sorted(sensitive, key=lambda e: len(e.text), reverse=True)
    text = detection.original_prompt
    modified = False

    for entity in ordered:
        if entity.text not in text:
            continue  # already replaced by a longer overlapping entity

        if entity.text in smap.original_to_placeholder:
            # Reuse existing placeholder from a previous turn
            placeholder = smap.original_to_placeholder[entity.text]
        else:
            # Assign a new placeholder
            tag = ENTITY_TAG.get(entity.entity_type, "ENTITY")
            smap.counters[tag] = smap.counters.get(tag, 0) + 1
            placeholder = f"{{{{{tag}_{smap.counters[tag]}}}}}"
            smap.original_to_placeholder[entity.text] = placeholder
            smap.placeholder_to_original[placeholder] = entity.text

        text = text.replace(entity.text, placeholder)
        modified = True

    return text, modified


# ---------------------------------------------------------------------------
# Remap (pure Python, no LLM)
# ---------------------------------------------------------------------------

def _remap(text: str, smap: _SessionMap) -> str:
    """
    Replace every placeholder in *text* with its original value.

    Uses the full session map, so placeholders from any previous turn are
    also restored.  Longest placeholders are processed first to avoid
    substring collisions (e.g. {{PERSON_10}} vs {{PERSON_1}}).
    """
    if not smap.placeholder_to_original:
        return text

    ordered = sorted(
        smap.placeholder_to_original.keys(),
        key=len,
        reverse=True,
    )

    result = text
    for placeholder in ordered:
        if placeholder in result:
            result = result.replace(placeholder, smap.placeholder_to_original[placeholder])

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_detector = PiiDetector()


async def sanitize_input(
    text: str,
    session_key: str,
    *,
    fail_open: bool = True,
) -> tuple[str, bool, list[DetectedEntity]]:
    """
    Detect PII in *text* and rewrite with placeholders.

    Parameters
    ----------
    text:
        Raw user message.
    session_key:
        Nanobot session key (e.g. "telegram:12345").  Used to look up and
        update the persistent placeholder mapping for this conversation.
    fail_open:
        When True (default), return the original text unmodified if the local
        LLM is unreachable.  Set to False to raise and block the message.

    Returns
    -------
    (sanitized_text, was_modified, redacted_entities)
        redacted_entities: entities that were actually substituted this turn.
        Empty list when nothing was modified or on fail-open.
    """
    try:
        detection = await _detector.detect(text)
    except Exception:
        if fail_open:
            logger.warning(
                "sanitizer: local LLM unavailable — passing message through unsanitized "
                "(session={})", session_key
            )
            return text, False, []
        raise

    smap = _load_map(session_key)
    sanitized, modified = _rewrite(detection, smap)

    if modified:
        _save_map(session_key, smap)
        logger.debug(
            "sanitizer: {} placeholder(s) applied (session={})",
            len(detection.sensitive_entities),
            session_key,
        )

    return sanitized, modified, detection.sensitive_entities if modified else []


async def remap_response(text: str, session_key: str) -> str:
    """
    Restore placeholders in the LLM response back to their original values.

    Uses the full accumulated session map so placeholders from any turn
    can be resolved.
    """
    smap = _load_map(session_key)
    result = _remap(text, smap)

    if result != text:
        logger.debug("sanitizer: response remapped (session={})", session_key)

    return result
