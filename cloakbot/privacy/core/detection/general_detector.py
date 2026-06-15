from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger
from pydantic import BaseModel

from cloakbot.privacy.core.detection.llm_json import JsonCompletionRunner, load_json_object
from cloakbot.privacy.core.types import REGISTRY, GeneralEntity

_DEDUPE_PLACEHOLDER_RE = re.compile(r"^<<[A-Z]+(?:_[A-Z]+)*_\d+>>$")
_DEDUPE_ELIGIBLE_TAGS = {"PERSON", "ORG"}

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
      "entity_type": "<{_ENUM_STR}>",
      "dedupe_hint": "<<PERSON_N>>" | "new"   // optional; only when the user prompt explicitly asks for cross-turn dedupe on this entity type
    }}
  ]
}}

If no sensitive general entities are found, use "entities": [].
Do NOT include the same entity text twice.
The `dedupe_hint` field is OPTIONAL. Only emit it when the user prompt
contains an explicit "Cross-turn dedupe" section, and only for PERSON or
ORG entities. Omit the field entirely in every other case."""

_PARTIAL_CANDIDATE_ENTITY_TYPES = {"person", "org"}


@dataclass(frozen=True)
class PartialCandidate:
    surface: str
    canonical: str
    entity_type: str


@dataclass(frozen=True)
class DedupeTarget:
    """A known person/org entity from the session Vault that the detector
    should consider when emitting a `dedupe_hint` for each freshly-detected
    PERSON / ORG span.

    `placeholder` is the existing token (e.g. ``"<<PERSON_1>>"``) the local
    detector may reference in its output to mean "this new mention refers to
    the SAME entity". `canonical` is the original surface (e.g.
    ``"Lin Zhiyuan"``) shown to the detector for context."""

    placeholder: str
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
                )
            )

    return candidates


def _build_system_prompt() -> str:
    return _GENERAL_SYSTEM_PROMPT


def _build_user_prompt(
    prompt: str,
    partial_candidates: list[PartialCandidate] | None = None,
    dedupe_targets: list[DedupeTarget] | None = None,
) -> str:
    sections: list[str] = []

    if partial_candidates:
        candidate_lines = "\n".join(
            (
                f'- "{candidate.surface}" may refer to known {candidate.entity_type} '
                f'"{candidate.canonical}" -> if so, extract "{candidate.surface}" '
                f"as: {candidate.entity_type}"
            )
            for candidate in partial_candidates
        )
        sections.append(
            "[Candidate partial mentions detected in the text - judge each one:]\n"
            f"{candidate_lines}\n"
            "Only extract the candidate if it clearly refers to the known entity in "
            "context. If ambiguous or unrelated, skip it."
        )

    if dedupe_targets:
        target_lines = "\n".join(
            f'- {target.placeholder}: "{target.canonical}" ({target.entity_type})'
            for target in dedupe_targets
        )
        sections.append(
            "[Cross-turn dedupe — known person/org entities from prior turns:]\n"
            f"{target_lines}\n"
            "For EACH person/org entity you extract, you MUST add a `dedupe_hint` "
            "field with EXACTLY one of:\n"
            "  • the matching placeholder above (e.g. \"<<PERSON_1>>\") — only "
            "when the new mention clearly refers to the SAME individual or "
            "organisation as that placeholder.\n"
            "  • the literal string \"new\" — when the mention is clearly a "
            "DIFFERENT entity (e.g. another person who happens to share a "
            "surname; a different company with a similar name; phrases like "
            "\"another\", \"a different\", \"someone surnamed X\", "
            "\"someone else named X\" almost always mean a NEW entity).\n"
            "  • omit the field entirely — only when truly ambiguous and you "
            "cannot tell.\n"
            "Worked example:\n"
            "  Known: <<PERSON_1>>: \"Lin Zhiyuan\" (person)\n"
            "  Text:  \"...also held by someone surnamed Lin.\"\n"
            "  Extract: {\"text\": \"Lin\", \"entity_type\": \"person\", "
            "\"dedupe_hint\": \"new\"}\n"
            "  (NOT \"<<PERSON_1>>\" — \"someone surnamed Lin\" explicitly "
            "signals a DIFFERENT individual who merely shares a surname.)\n"
            "Over-merging two distinct people onto one placeholder silently "
            "corrupts downstream restoration; when in real doubt, choose "
            "\"new\" rather than the placeholder."
        )

    if not sections:
        return prompt

    return "\n\n".join(sections) + f"\n\nText to analyze:\n{prompt}"


class GeneralDetectionResult(BaseModel):
    raw_output: str
    entities: list[GeneralEntity]
    latency_ms: float


class GeneralPrivacyDetector:
    """Detect general sensitive entities, excluding computable math elements."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._runner = JsonCompletionRunner(temperature=temperature)

    async def detect(
        self,
        prompt: str,
        *,
        partial_candidates: list[PartialCandidate] | None = None,
        dedupe_targets: list[DedupeTarget] | None = None,
    ) -> GeneralDetectionResult:
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(prompt, partial_candidates, dedupe_targets)
        valid_dedupe_placeholders = {t.placeholder for t in dedupe_targets or []}
        logger.debug(
            "GeneralPrivacyDetector prompt built: partial_candidate_count={} "
            "partial_candidate_types={} candidate_section={} "
            "dedupe_target_count={} dedupe_section={} "
            "system_prompt_chars={} user_prompt_chars={}",
            _partial_candidate_count(partial_candidates),
            _partial_candidate_types(partial_candidates),
            "Candidate partial mentions detected" in user_prompt,
            len(dedupe_targets or []),
            "Cross-turn dedupe" in user_prompt,
            len(system_prompt),
            len(user_prompt),
        )
        raw_output, latency_ms = await self._runner.complete(
            system_prompt,
            user_prompt,
        )
        entities = parse_general_entities(
            raw_output,
            prompt,
            valid_dedupe_placeholders=valid_dedupe_placeholders,
        )
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
            raw_output=raw_output, entities=entities, latency_ms=latency_ms
        )


def parse_general_entities(
    raw_output: str,
    prompt: str,
    *,
    valid_dedupe_placeholders: set[str] | None = None,
) -> list[GeneralEntity]:
    data = load_json_object(raw_output)
    if not data:
        return []

    seen: set[str] = set()
    entities: list[GeneralEntity] = []
    valid_placeholders = valid_dedupe_placeholders or set()

    for item in data.get("entities", []):
        try:
            text = str(item["text"])
            slug = str(item["entity_type"])
            if slug not in _VALID_ENTITY_TYPES:
                continue
            if text in seen or prompt.find(text) == -1:
                continue

            seen.add(text)
            entities.append(
                GeneralEntity(
                    text=text,
                    entity_type=slug,
                    dedupe_hint=_parse_dedupe_hint(item, slug, valid_placeholders),
                )
            )
        except (KeyError, ValueError):
            logger.debug("GeneralPrivacyDetector: skipping malformed entity: {}", item)
            continue

    return entities


def _parse_dedupe_hint(
    item: dict,
    slug: str,
    valid_placeholders: set[str],
) -> str | None:
    """Validate and normalise the optional `dedupe_hint` field emitted by the
    local model. Returns `None` for any malformed or non-eligible hint so the
    sanitizer falls back to the legacy substring resolver path."""
    raw = item.get("dedupe_hint")
    if not raw:
        return None
    if not isinstance(raw, str):
        return None
    hint = raw.strip()
    if not hint:
        return None
    # Only PERSON / ORG go through cross-turn dedupe. Any hint on a
    # non-eligible entity type is meaningless and we discard it.
    tag = REGISTRY.tag_map.get(slug, "")
    if tag not in _DEDUPE_ELIGIBLE_TAGS:
        return None
    if hint.lower() == "new":
        return "new"
    if _DEDUPE_PLACEHOLDER_RE.fullmatch(hint) and hint in valid_placeholders:
        return hint
    return None


def _partial_candidate_count(partial_candidates: list[PartialCandidate] | None) -> int:
    return len(partial_candidates or [])


def _partial_candidate_types(partial_candidates: list[PartialCandidate] | None) -> list[str]:
    types: set[str] = set()
    for candidate in partial_candidates or []:
        types.add(candidate.entity_type)
    return sorted(types)
