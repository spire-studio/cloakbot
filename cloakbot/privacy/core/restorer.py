"""Privacy token restoration helpers."""

from __future__ import annotations

import re

from pydantic import BaseModel

from cloakbot.privacy.core.math_executer import LocalComputationRecord
from cloakbot.privacy.core.types import REGISTRY, Severity
from cloakbot.privacy.core.vault import PLACEHOLDER_RE, _SessionMap


class RestoredTokenAnnotation(BaseModel):
    annotation_type: str = "entity"
    placeholder: str
    text: str
    start: int
    end: int
    entity_type: str
    severity: Severity
    canonical: str
    aliases: list[str]
    value: int | float | str | None = None
    formula: str | None = None


def restore_tokens(text: str, smap: _SessionMap) -> str:
    """
    Replace every ``<<TOKEN>>`` placeholder in *text* with its original value
    in a single regex pass.

    A single ``re.sub`` call with a lookup callback eliminates ordering issues
    (e.g. ``<<PERSON_10>>`` vs ``<<PERSON_1>>``) and avoids the corruption
    problems inherent in iterative ``str.replace`` approaches.
    """
    if not smap.placeholder_to_original and not smap.placeholder_to_entity:
        return text

    def _replace(m: re.Match) -> str:
        token = m.group(0)  # e.g. "<<PERSON_1>>"
        return smap.display_value(token)

    return PLACEHOLDER_RE.sub(_replace, text)


def restore_tokens_with_annotations(
    text: str,
    smap: _SessionMap,
) -> tuple[str, list[RestoredTokenAnnotation]]:
    """Restore tokens and return metadata for each visible restored span."""
    if not smap.placeholder_to_original and not smap.placeholder_to_entity:
        return text, []

    parts: list[str] = []
    annotations: list[RestoredTokenAnnotation] = []
    cursor = 0
    output_len = 0

    for match in PLACEHOLDER_RE.finditer(text):
        if match.start() > cursor:
            chunk = text[cursor:match.start()]
            parts.append(chunk)
            output_len += len(chunk)

        token = match.group(0)
        restored = smap.display_value(token)
        parts.append(restored)

        if restored != token:
            entity = smap.placeholder_to_entity.get(token)
            canonical = entity.canonical if entity is not None else smap.placeholder_to_original.get(token, restored)
            entity_type = entity.entity_type if entity is not None else _entity_type_from_placeholder(token)
            annotations.append(
                RestoredTokenAnnotation(
                    placeholder=token,
                    text=restored,
                    start=output_len,
                    end=output_len + len(restored),
                    entity_type=entity_type,
                    severity=REGISTRY.severity_map.get(entity_type, Severity.MEDIUM),
                    canonical=canonical,
                    aliases=list(entity.aliases) if entity is not None else [canonical],
                    value=entity.value if entity is not None else smap.placeholder_to_value.get(token),
                )
            )

        output_len += len(restored)
        cursor = match.end()

    if cursor < len(text):
        parts.append(text[cursor:])

    return "".join(parts), annotations


def build_local_computation_annotations(
    text: str,
    computations: list[LocalComputationRecord],
) -> list[RestoredTokenAnnotation]:
    """Annotate visible local computation results in output text."""
    annotations: list[RestoredTokenAnnotation] = []
    cursor = 0

    for computation in computations:
        result_text = computation.formatted_result
        if not result_text:
            continue

        start = text.find(result_text, cursor)
        if start < 0:
            continue

        end = start + len(result_text)
        annotations.append(
            RestoredTokenAnnotation(
                annotation_type="local_computation",
                placeholder=f"<python_snippet_{computation.snippet_index}>",
                text=result_text,
                start=start,
                end=end,
                entity_type="local_computation",
                severity=Severity.LOW,
                canonical=result_text,
                aliases=[],
                value=computation.result,
                formula=computation.resolved_expression,
            )
        )
        cursor = end

    return annotations


def _entity_type_from_placeholder(placeholder: str) -> str:
    match = re.fullmatch(r"<<([A-Z]+(?:_[A-Z]+)*)_\d+>>", placeholder)
    if not match:
        return "entity"
    return match.group(1).lower()
