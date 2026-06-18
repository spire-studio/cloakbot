"""Public facade for the visual privacy redaction pipeline.

The pipeline is split into cohesive submodules, each importable on its own but
presented here as one cohesive API so callers depend on "visual redaction", not
its internals:

- :mod:`models`    — dependency-free data models (records, regions, results).
- :mod:`labels`    — visual-label ↔ registry-tag translation tables.
- :mod:`detector`  — the remote multimodal detector (prompt, call, JSON parse).
- :mod:`ocr_match` — local OCR extraction, normalization, fuzzy bbox matching.
- :mod:`render`    — region-map text + PIL redaction-box drawing.
- :mod:`pipeline`  — vault-orchestrating ``process_visual_blocks`` and friends.

Import everything from here (``cloakbot.privacy.visual_redaction``). Internal,
underscore-prefixed helpers live on their owning submodule and are reached there
directly (e.g. tests patch ``...visual_redaction.detector._inspect_visual``). The
``<<TAG_N>>`` placeholder grammar itself lives in
:mod:`cloakbot.privacy.core.placeholders`.

Trust boundary (enforced in :mod:`pipeline`): raw sensitive values are never
forwarded to the remote LLM path. The detector only proposes regions; a box is
drawn only after local OCR confirms it; the pipeline fails closed otherwise.
"""

from __future__ import annotations

from cloakbot.privacy.visual_redaction.labels import (
    text_entity_type_to_visual_label,
    visual_label_to_tag,
)
from cloakbot.privacy.visual_redaction.models import (
    VisualBlocksResult,
    VisualPrivacyRedaction,
    VisualRedactedRegion,
    VisualVaultEntry,
)
from cloakbot.privacy.visual_redaction.ocr_match import normalize_ocr_text
from cloakbot.privacy.visual_redaction.pipeline import (
    extract_visual_image,
    extract_visual_text,
    is_visual_content_blocks,
    process_visual_blocks,
    redact_visual_content_blocks,
)

__all__ = [
    "VisualBlocksResult",
    "VisualPrivacyRedaction",
    "VisualRedactedRegion",
    "VisualVaultEntry",
    "extract_visual_image",
    "extract_visual_text",
    "is_visual_content_blocks",
    "normalize_ocr_text",
    "process_visual_blocks",
    "redact_visual_content_blocks",
    "text_entity_type_to_visual_label",
    "visual_label_to_tag",
]
