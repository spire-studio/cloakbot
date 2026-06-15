from __future__ import annotations

from enum import Enum
from typing import Dict, List, Union

from pydantic import BaseModel, Field, computed_field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EntitySpec(BaseModel):
    slug: str
    tag: str
    description: str
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    severity: Severity = Severity.HIGH


class PrivacyRegistry(BaseModel):
    general: List[EntitySpec]
    computable: List[EntitySpec]

    def get_prompt_block(self, category: str) -> str:
        specs = getattr(self, category)
        blocks: list[str] = []
        for spec in specs:
            lines = [
                f"{spec.slug}:",
                f"  Meaning: {spec.description}",
            ]
            if spec.include:
                lines.append(f"  Include: {', '.join(spec.include)}")
            if spec.exclude:
                lines.append(f"  Exclude: {', '.join(spec.exclude)}")
            if spec.examples:
                lines.append(f"  Examples: {'; '.join(spec.examples)}")
            blocks.append("\n".join(lines))
        return "\n".join(blocks)

    def get_enum_str(self, category: str) -> str:
        specs = getattr(self, category)
        return "|".join(s.slug for s in specs)

    @property
    def tag_map(self) -> Dict[str, str]:
        return {s.slug: s.tag for s in self.general + self.computable}

    @property
    def severity_map(self) -> Dict[str, Severity]:
        return {s.slug: s.severity for s in self.general + self.computable}

    @property
    def computable_tags(self) -> List[str]:
        return [s.tag for s in self.computable]


REGISTRY = PrivacyRegistry(
    general=[
        EntitySpec(
            slug="person",
            tag="PERSON",
            description="people mentioned in a private user context",
            include=["full names", "first names", "last names", "handles", "nicknames", "aliases"],
            exclude=["roles", "pronouns"],
        ),
        EntitySpec(slug="phone", tag="PHONE", description="phone numbers"),
        EntitySpec(slug="email", tag="EMAIL", description="email addresses"),
        EntitySpec(
            slug="identifier",
            tag="ID",
            description="private compact reference codes including usernames and handles that identify a specific account",
            include=["account IDs", "invoice IDs", "loan IDs", "ticket IDs", "case refs", "account endings", "usernames", "login handles"],
            exclude=["money", "dates", "percentages", "plain numbers", "field labels", "template versions"],
            examples=[
                "ACCT-78294013",
                "INV-2024-A8K3",
                "T-512674",
                "jsmith2024",
                "john.doe",
                "case ref #4731",
            ],
        ),
        EntitySpec(
            slug="address",
            tag="ADDRESS",
            description="private physical locations; extract the full multi-token span (street number through ZIP) as ONE entity",
            include=["street addresses", "mailing addresses", "units", "postal codes", "city+state+ZIP groupings"],
            exclude=["organization names"],
            examples=[
                "65423 Garcia Light, West Melanieview, AS 06196",
                "1600 Pennsylvania Ave NW, Washington, DC 20500",
                "Apt 5B, 245 Morgan Stream, Heidiville, ID 05939",
            ],
        ),
        EntitySpec(
            slug="credential",
            tag="CREDENTIAL",
            description="private access secrets",
            include=["passwords", "API keys", "auth tokens", "secret phrases"],
        ),
        EntitySpec(slug="ip_address", tag="IP", description="IPv4 or IPv6 addresses"),
        EntitySpec(
            slug="url",
            tag="URL",
            description="private or sensitive links",
            include=["portals", "upload links", "private domains"],
            exclude=["public sites"],
        ),
        EntitySpec(
            slug="local_path",
            tag="LOCAL_PATH",
            description="local filesystem paths or file URLs on the user's machine",
            include=["absolute paths", "relative paths", "home-directory paths", "file:// URLs"],
            exclude=["http URLs", "https URLs"],
        ),
        EntitySpec(
            slug="medical",
            tag="MEDICAL",
            description="private health information; keep drug+dose+schedule together as one span",
            include=["diagnoses", "treatments", "medications with dosage", "insurance plans", "patient details"],
            examples=[
                "hypertension",
                "atrial fibrillation",
                "asthma",
                "type 2 diabetes",
                "stage 2 chronic kidney disease",
                "Atorvastatin 40mg nightly",
                "Metformin 500mg twice daily",
                "Apixaban 5mg twice daily",
                "BlueCross PPO",
            ],
        ),
        EntitySpec(
            slug="org",
            tag="ORG",
            description="organization names mentioned in a private user context; extract even when the name reads like a personal name (hyphenated surnames, partner-style names, single-surname + corporate suffix)",
            include=["companies", "vendors", "lenders", "payroll firms", "credit unions", "banks", "clinics", "schools"],
            exclude=["street addresses"],
            examples=[
                "Hall PLC",
                "Acme Corp",
                "Globex LLC",
                "Taylor-Simmons",
                "Miller, Henderson and Johnson",
                "BlueCross",
                "Kaiser Permanente",
            ],
        ),
    ],
    computable=[
        EntitySpec(
            slug="financial",
            tag="FINANCE",
            description="private money amounts",
            include=["salary", "rent", "debt", "balance", "budget", "invoice amounts"],
        ),
        EntitySpec(
            slug="temporal",
            tag="DATE",
            description="private time references",
            include=["dates", "times", "deadlines", "milestones"],
            exclude=["public years", "template years"],
        ),
        EntitySpec(
            slug="percentage",
            tag="PERCENTAGE",
            description="private percentage values",
            include=["rates", "shares", "percentage targets"],
        ),
        EntitySpec(
            slug="amount",
            tag="AMOUNT",
            description="standalone private counts or ratios",
            include=["counts", "ratios"],
            exclude=["IDs", "labels", "template numbers", "ZIP codes (part of address)", "street numbers (part of address)"],
        ),
        EntitySpec(
            slug="measurement",
            tag="METRIC",
            description="private metrics with units",
            include=["physical metrics", "medical vitals", "scientific results"],
            exclude=["medication dosages (covered by medical)", "ZIP codes", "street numbers"],
        ),
        EntitySpec(
            slug="value",
            tag="VALUE",
            description="private numeric values",
            include=["scores", "ratings", "ages", "demographics", "coordinates"],
            exclude=["IDs", "money", "dates", "template numbers", "labels", "ZIP codes (part of address)", "street numbers (part of address)"],
        ),
    ],
)


class GeneralEntity(BaseModel):
    """PII without computable value."""

    text: str
    entity_type: str
    # Optional cross-turn dedupe decision produced by the local detector.
    # One of:
    #   - "new" — the local model judged this is a NEW distinct entity
    #     (e.g. "someone surnamed Lin" when a different Lin Zhiyuan is
    #     already in the Vault). The sanitizer MUST allocate a fresh
    #     placeholder and MUST NOT fall through to the substring alias
    #     resolver.
    #   - "<<PERSON_N>>" / "<<ORG_N>>" — the local model judged this is
    #     the SAME entity as the given existing placeholder. The
    #     sanitizer reuses that placeholder verbatim (after validating
    #     it actually exists in the smap).
    #   - None — the model gave no decision; fall back to the legacy
    #     substring alias resolver behavior. This preserves backwards
    #     compatibility for detectors / paths that don't emit the hint.
    dedupe_hint: str | None = None

    @computed_field
    @property
    def severity(self) -> Severity:
        return REGISTRY.severity_map.get(self.entity_type, Severity.MEDIUM)


class ComputableEntity(BaseModel):
    """Entity with normalized value (int, float, or str) for logic/math."""

    text: str
    entity_type: str
    value: int | float | str  # Polymorphic: "10%" -> 0.1, "2023-10-01" -> str

    @computed_field
    @property
    def severity(self) -> Severity:
        return REGISTRY.severity_map.get(self.entity_type, Severity.MEDIUM)


# Discriminated Union for Pydantic v2
DetectedEntity = Union[GeneralEntity, ComputableEntity]


class DetectionResult(BaseModel):
    original_prompt: str
    entities: List[DetectedEntity]
    llm_raw_output: str
    latency_ms: float

    @property
    def has_sensitive_data(self) -> bool:
        return bool(self.entities)

    @property
    def sensitive_entities(self) -> List[DetectedEntity]:
        return self.entities


__all__ = [
    "REGISTRY",
    "GeneralEntity",
    "ComputableEntity",
    "DetectedEntity",
    "DetectionResult",
    "Severity",
]
