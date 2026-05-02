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
            description="private compact reference codes",
            include=["account IDs", "invoice IDs", "loan IDs", "ticket IDs", "case refs", "account endings"],
            exclude=["money", "dates", "percentages", "plain numbers", "field labels", "template versions"],
        ),
        EntitySpec(
            slug="address",
            tag="ADDRESS",
            description="private physical locations",
            include=["street addresses", "mailing addresses", "units", "postal codes"],
            exclude=["organization names"],
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
            slug="medical",
            tag="MEDICAL",
            description="private health information",
            include=["diagnoses", "treatments", "insurance", "patient details"],
        ),
        EntitySpec(
            slug="org",
            tag="ORG",
            description="organization names mentioned in a private user context",
            include=["companies", "vendors", "lenders", "payroll firms", "credit unions", "banks", "clinics", "schools"],
            exclude=["street addresses"],
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
            exclude=["IDs", "labels", "template numbers", "address parts"],
        ),
        EntitySpec(
            slug="measurement",
            tag="METRIC",
            description="private metrics with units",
            include=["physical metrics", "medical vitals", "scientific results"],
        ),
        EntitySpec(
            slug="value",
            tag="VALUE",
            description="private numeric values",
            include=["scores", "ratings", "ages", "demographics", "coordinates"],
            exclude=["IDs", "money", "dates", "template numbers", "labels"],
        ),
    ],
)


class GeneralEntity(BaseModel):
    """PII without computable value."""

    text: str
    entity_type: str

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
