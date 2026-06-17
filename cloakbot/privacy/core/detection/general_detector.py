from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings

from cloakbot.privacy.core.detection.detector_model import (
    build_detector_model,
    response_text,
)
from cloakbot.privacy.core.types import REGISTRY, GeneralEntity

_TYPE_BLOCK = REGISTRY.get_prompt_block("general")
_ENUM_STR = REGISTRY.get_enum_str("general")
_VALID_ENTITY_TYPES = {spec.slug for spec in REGISTRY.general}

_GENERAL_SYSTEM_PROMPT = f"""You are a privacy-focused general entity extractor.

━━━ System Architecture & Misson ━━━
You act as a local privacy-preserving proxy. The general entities you extract will be masked/anonymized before the sanitized prompt is sent to an untrusted remote LLM.
The remote LLM's job is to answer the user's request while preserving task intent. Therefore, you MUST preserve the task structure and instructions, extracting ONLY sensitive non-computable entity values.

━━━ Strict Rules ━━━
1. Extract only sensitive NON-COMPUTABLE entity values.
2. Each extracted entity must be an exact substring from the input.
3. Instructional Bypass: Do NOT extract task instructions, formatting requirements, structural requests, or output constraints.
4. Public Data Bypass: Do NOT extract public entities unless they act as private identifiers in context.
5. Do NOT extract slot phrases or field references such as: "my name" in "What is my name", "my email" in "Send my email to Alice".
6. Never extract money, dates, times, percentages, counts, measurements, or plain numbers; the numeric detector handles private numeric values.
7. Use identifier only for compact reference codes or explicit account endings; never for spans with "$", "%", month names, or date formats.
8. Extract private-context organizations and person names, including standalone aliases or first names when they clearly refer to a private person in the prompt.

━━━ Document-context recall ━━━
In a structured document bound to a private party (invoice, receipt, statement, contract, order; possibly OCR'd), extract its private surfaces aggressively — do not skip a repeated value as "templated":

9. Lines under a party header ("Bill To" / "Ship To" / "From"-style), up to the next blank line or column header → **org** / **address** (full multi-line span) / **person** (the customer slot).
10. A named payment processor next to a transaction → **org**.
11. A long compound transaction / order id (alphanumeric run joined by "|" "-" "_" ".") or an internal-looking service / instance code → **identifier**, as ONE span.
12. Clinical context → **medical** (diagnosis, drug+dose, treatment, insurance) bound to a person; keep drug+dose+schedule as ONE span (overrides Rule 6).

Additive to Rules 1–8; see each type's Examples below.

━━━ Entity types ━━━
{_TYPE_BLOCK}

━━━ Output format ━━━
Return ONLY valid JSON.
{{
  "entities": [
    {{
      "text": "<exact substring from input, unchanged>",
      "entity_type": "<{_ENUM_STR}>"
    }}
  ]
}}

If no sensitive general entities are found, use "entities": [].
Do NOT include the same entity text twice."""

_PARTIAL_CANDIDATE_ENTITY_TYPES = {"person", "org"}


@dataclass(frozen=True)
class PartialCandidate:
    surface: str
    canonical: str
    entity_type: str


def scan_partial_candidates(
    text: str,
    vault_entries: list[dict[str, str]],
) -> list[PartialCandidate]:
    candidates: list[PartialCandidate] = []
    seen: set[tuple[str, str]] = set()

    for entry in vault_entries:
        canonical = str(entry.get("canonical", "")).strip()
        entity_type = str(entry.get("type", "")).strip()
        if not canonical or entity_type not in _PARTIAL_CANDIDATE_ENTITY_TYPES:
            continue

        surfaces_for_canonical: set[str] = set()
        for token in canonical.split():
            surface = token.strip()
            if len(surface) < 2:
                continue
            if surface == canonical:
                continue
            if surface not in text:
                continue
            if surface in surfaces_for_canonical:
                continue
            surfaces_for_canonical.add(surface)

            key = (canonical, surface)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                PartialCandidate(
                    surface=surface,
                    canonical=canonical,
                    entity_type=entity_type,
                ),
            )

    return candidates


def _build_system_prompt() -> str:
    return _GENERAL_SYSTEM_PROMPT


def _build_user_prompt(
    prompt: str,
    partial_candidates: list[PartialCandidate] | None = None,
) -> str:
    if not partial_candidates:
        return prompt

    candidate_lines = "\n".join(
        (
            f'- "{candidate.surface}" may refer to known {candidate.entity_type} '
            f'"{candidate.canonical}" -> if so, extract "{candidate.surface}" '
            f"as: {candidate.entity_type}"
        )
        for candidate in partial_candidates
    )
    section = (
        "[Candidate partial mentions detected in the text - judge each one:]\n"
        f"{candidate_lines}\n"
        "Only extract the candidate if it clearly refers to the known entity in "
        "context. If ambiguous or unrelated, skip it."
    )
    return f"{section}\n\nText to analyze:\n{prompt}"


class GeneralDetection(BaseModel):
    """Structured output target for the general detector LLM call."""

    entities: list[GeneralEntity] = []


class GeneralDetectionResult(BaseModel):
    raw_output: str
    entities: list[GeneralEntity]
    latency_ms: float


_GENERAL_AGENT = Agent(
    output_type=NativeOutput(GeneralDetection),
    instructions=_GENERAL_SYSTEM_PROMPT,
    deps_type=str,
    retries=1,
)


@_GENERAL_AGENT.output_validator
def _enforce_general_invariants(ctx: RunContext[str], out: GeneralDetection) -> GeneralDetection:
    """Apply the privacy-bearing filters to the model's structured output.

    Deterministic backstops: each span must be a verbatim substring of the
    source (``ctx.deps``), of a known entity type, and de-duplicated. Never
    delegated to a retry.
    """
    return GeneralDetection(entities=normalize_general_entities(out.entities, ctx.deps))


def normalize_general_entities(
    entities: list[GeneralEntity],
    prompt: str,
) -> list[GeneralEntity]:
    """Keep only valid, in-prompt, de-duplicated entities."""
    seen: set[str] = set()
    kept: list[GeneralEntity] = []
    for entity in entities:
        slug = entity.entity_type
        if slug not in _VALID_ENTITY_TYPES:
            continue
        if entity.text in seen or entity.text not in prompt:
            continue
        seen.add(entity.text)
        kept.append(GeneralEntity(text=entity.text, entity_type=slug))
    return kept


class GeneralPrivacyDetector:
    """Detect general sensitive entities, excluding computable math elements."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._temperature = temperature

    async def detect(
        self,
        prompt: str,
        *,
        partial_candidates: list[PartialCandidate] | None = None,
    ) -> GeneralDetectionResult:
        user_prompt = _build_user_prompt(prompt, partial_candidates)
        logger.debug(
            "GeneralPrivacyDetector prompt built: partial_candidate_count={} "
            "partial_candidate_types={} candidate_section={} "
            "system_prompt_chars={} user_prompt_chars={}",
            _partial_candidate_count(partial_candidates),
            _partial_candidate_types(partial_candidates),
            "Candidate partial mentions detected" in user_prompt,
            len(_GENERAL_SYSTEM_PROMPT),
            len(user_prompt),
        )

        t0 = time.perf_counter()
        try:
            result = await _GENERAL_AGENT.run(
                user_prompt,
                deps=prompt,
                model=build_detector_model(),
                model_settings=ModelSettings(temperature=self._temperature),
            )
            entities = result.output.entities
            raw_output = response_text(result)
        except UnexpectedModelBehavior:
            logger.warning(
                "GeneralPrivacyDetector: local model returned unparseable output; "
                "treating as no entities",
            )
            entities, raw_output = [], ""
        latency_ms = (time.perf_counter() - t0) * 1000

        logger.debug(
            "GeneralPrivacyDetector response parsed: raw_chars={} entity_count={} entities={}",
            len(raw_output),
            len(entities),
            [
                {"entity_type": entity.entity_type, "text_chars": len(entity.text)}
                for entity in entities
            ],
        )
        return GeneralDetectionResult(
            raw_output=raw_output, entities=entities, latency_ms=latency_ms,
        )


def _partial_candidate_count(partial_candidates: list[PartialCandidate] | None) -> int:
    return len(partial_candidates or [])


def _partial_candidate_types(partial_candidates: list[PartialCandidate] | None) -> list[str]:
    types: set[str] = set()
    for candidate in partial_candidates or []:
        types.add(candidate.entity_type)
    return sorted(types)
