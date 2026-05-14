from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from pydantic import BaseModel

from cloakbot.privacy.core.detection.llm_json import JsonCompletionRunner, load_json_object
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

━━━ Document-context recall hints ━━━
The text may be an OCR'd invoice, receipt, bill, contract, or order — i.e. a structured document tied to a specific private party. In these documents, be **aggressive** about extracting the following surfaces (do not dismiss them as "templated" or "public"):

9. Invoice / receipt section labels — "Pay To", "Invoiced To", "Bill To", "Ship To", "Sold To", "From", "To" — are followed by an organisation or person and an address. Treat every non-empty line beneath such a label, up to the next blank line or column header, as a candidate for extraction:
   - Organisation lines (e.g. "DMIT, Inc.", "Acme Corp", "Anthropic PBC") → **org**.
   - Address lines (street, city, state/region, postal code, country) → **address**, even when split across multiple lines.
   - Personal names appearing in the customer slot → **person**.
10. Payment gateway / processor names appearing next to a transaction (Alipay, WeChat Pay, Stripe, PayPal, Square, Adyen, Braintree, UnionPay, ApplePay, GooglePay) → **org**, because their presence reveals the customer's payment relationship.
11. Long compound transaction / order identifiers — typically ≥16 alphanumeric chars, often containing "|", "-", "_", or "." separators (e.g. "2026043022001359301458224680|AHVBS6N2UDFC-JIWGK-8896153") → **identifier**. Extract the entire span as a single entity; do not split.
12. Service / product / instance codes that look like internal labels (e.g. "LAX.AN4.Pro.TINY", "DMIT-US-1", "us-west-2-i-0a1b2c3d") → **identifier** when they appear in a customer-facing document (invoice line item, receipt, contract).
13. URLs, file paths, account / API hostnames embedded in invoice or receipt descriptions follow the existing url / local_path rules — extract them as usual.
14. Clinical context — when the prompt discusses healthcare, doctors, prescriptions, insurance, or patient care, be aggressive about extracting **medical** surfaces (diagnoses, drug+dose phrases, treatments, insurance plans) bound to a specific person. See the `medical` Examples below for canonical shapes. The full drug+dose+schedule phrase stays as ONE span — this overrides Rule 6 for medication spans that embed a dose.

These hints are additive — they do not override Rules 1–8. If a surface looks "templated" but only because the OCR layout repeats it (e.g. the same customer address on every page), still extract it.

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
                )
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
    return (
        "[Candidate partial mentions detected in the text - judge each one:]\n"
        f"{candidate_lines}\n"
        "Only extract the candidate if it clearly refers to the known entity in "
        "context. If ambiguous or unrelated, skip it.\n\n"
        f"Text to analyze:\n{prompt}"
    )


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
    ) -> GeneralDetectionResult:
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(prompt, partial_candidates)
        logger.debug(
            "GeneralPrivacyDetector prompt built: partial_candidate_count={} "
            "partial_candidate_types={} candidate_section={} system_prompt_chars={} "
            "user_prompt_chars={}",
            _partial_candidate_count(partial_candidates),
            _partial_candidate_types(partial_candidates),
            "Candidate partial mentions detected" in user_prompt,
            len(system_prompt),
            len(user_prompt),
        )
        raw_output, latency_ms = await self._runner.complete(
            system_prompt,
            user_prompt,
        )
        entities = parse_general_entities(raw_output, prompt)
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


def parse_general_entities(raw_output: str, prompt: str) -> list[GeneralEntity]:
    data = load_json_object(raw_output)
    if not data:
        return []

    seen: set[str] = set()
    entities: list[GeneralEntity] = []

    for item in data.get("entities", []):
        try:
            text = str(item["text"])
            slug = str(item["entity_type"])
            if slug not in _VALID_ENTITY_TYPES:
                continue
            if text in seen or prompt.find(text) == -1:
                continue

            seen.add(text)
            entities.append(GeneralEntity(text=text, entity_type=slug))
        except (KeyError, ValueError):
            logger.debug("GeneralPrivacyDetector: skipping malformed entity: {}", item)
            continue

    return entities


def _partial_candidate_count(partial_candidates: list[PartialCandidate] | None) -> int:
    return len(partial_candidates or [])


def _partial_candidate_types(partial_candidates: list[PartialCandidate] | None) -> list[str]:
    types: set[str] = set()
    for candidate in partial_candidates or []:
        types.add(candidate.entity_type)
    return sorted(types)
