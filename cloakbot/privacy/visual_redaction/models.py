"""Dependency-free data models for the visual privacy pipeline.

These are the leaf types every other submodule depends on. Keeping them in a
module that imports nothing from the rest of the package lets callers (and the
``tool_models`` boundary) import :class:`VisualPrivacyRedaction` and
:class:`VisualVaultEntry` without dragging in PIL / pytesseract / the detector
client — and removes the lazy ``VisualVaultEntry`` import that the monolith used
to dodge a cycle.

Invariants:

* ``matched_text`` on :class:`VisualRedactedRegion` is the OCR-extracted anchor
  token kept for transparency reports only — never the raw PII value, and never
  forwarded to a remote model.
* :class:`VisualVaultEntry` stays a plain dataclass so it can be imported by
  ``cloakbot.privacy.tool_models`` (which itself imports
  :class:`VisualPrivacyRedaction`) without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VisualRedactedRegion(BaseModel):
    """One bbox-level redaction on an image, optionally bound to a vault placeholder.

    The placeholder is what makes the redaction transparent to a remote
    multimodal model: the box renders the placeholder token (e.g.
    ``<<PERSON_1>>``) instead of an opaque black bar, and the same token
    appears in the textual region-map alongside the image, so the model
    can refer to "the person in <<PERSON_1>>" and the local restorer
    swaps it back to the real value in the user-facing reply.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    placeholder: str | None = None
    bbox: list[int]
    label: str
    # ``matched_text`` is retained for transparency reports only. It is
    # the OCR-extracted token that anchored this region — never the raw
    # PII value as it appeared in the image. Callers must not surface
    # it to remote models.
    matched_text: str | None = None


class VisualPrivacyRedaction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_path: str | None = Field(default=None, alias="sourcePath")
    status: str
    detected_items: int = Field(alias="detectedItems")
    redaction_boxes: int = Field(alias="redactionBoxes")
    labels: list[str] = Field(default_factory=list)
    reason: str | None = None
    regions: list[VisualRedactedRegion] = Field(default_factory=list)


@dataclass(frozen=True)
class _TextWord:
    text: str
    token: str
    bbox: list[int]


@dataclass(frozen=True)
class VisualVaultEntry:
    """Vault-bound artifact produced by visual processing.

    Kept as a plain dataclass to avoid a circular import with
    ``cloakbot.privacy.tool_models`` (which itself imports
    :class:`VisualPrivacyRedaction` from this package). Callers convert these
    into ``ToolVaultArtifact`` instances at the boundary.
    """

    kind: str
    path: str
    media_type: str | None = None


@dataclass
class VisualBlocksResult:
    """Outcome of running the visual privacy pipeline over content blocks."""

    redacted_blocks: list[dict[str, Any]] = field(default_factory=list)
    sanitized_text: str = ""
    modified: bool = False
    entities: list[Any] = field(default_factory=list)
    visual_redactions: list[VisualPrivacyRedaction] = field(default_factory=list)
    vault_entries: list[VisualVaultEntry] = field(default_factory=list)
    omitted_count: int = 0
    image_count: int = 0


__all__ = [
    "VisualBlocksResult",
    "VisualPrivacyRedaction",
    "VisualRedactedRegion",
    "VisualVaultEntry",
    "_TextWord",
]
