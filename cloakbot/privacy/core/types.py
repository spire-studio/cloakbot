from __future__ import annotations

from enum import Enum
from typing import Dict, List, Union

from pydantic import BaseModel, computed_field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EntitySpec(BaseModel):
    slug: str
    tag: str
    description: str
    severity: Severity = Severity.HIGH


class PrivacyRegistry(BaseModel):
    general: List[EntitySpec]
    computable: List[EntitySpec]

    def get_prompt_block(self, category: str) -> str:
        specs = getattr(self, category)
        return "\n".join(f"  {s.slug:<20} – {s.description}" for s in specs)

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
            slug="person", tag="PERSON", description="names of individuals, handles, or pseudonyms."
        ),
        EntitySpec(slug="phone", tag="PHONE", description="phone numbers"),
        EntitySpec(slug="email", tag="EMAIL", description="email addresses"),
        EntitySpec(
            slug="identifier",
            tag="ID",
            description="unique IDs (SSN, passport, account, license plate)",
        ),
        EntitySpec(
            slug="address",
            tag="ADDRESS",
            description="physical addresses or specific locations",
        ),
        EntitySpec(
            slug="credential",
            tag="CREDENTIAL",
            description="passwords, API keys, secrets, tokens",
        ),
        EntitySpec(slug="ip_address", tag="IP", description="network identifiers (IPv4 or IPv6)"),
        EntitySpec(
            slug="url",
            tag="URL",
            description="sensitive or private links and domains",
        ),
        EntitySpec(
            slug="medical",
            tag="MEDICAL",
            description="health statuses, PHI, treatments",
        ),
        EntitySpec(
            slug="org",
            tag="ORG",
            description="names of companies, schools, or NGOs",
        ),
        EntitySpec(
            slug="sensitive_text",
            tag="DETAIL",
            description="private plans, secrets, or project code names",
        ),
    ],
    computable=[
        EntitySpec(
            slug="financial",
            tag="FINANCE",
            description="amounts of money, salaries, debts, budgets",
        ),
        EntitySpec(
            slug="temporal",
            tag="DATE",
            description="specific dates, timestamps, deadlines, milestones",
        ),
        EntitySpec(
            slug="percentage",
            tag="PERCENTAGE",
            description="percentages, percentage shares, or percentage rates",
        ),
        EntitySpec(
            slug="amount",
            tag="AMOUNT",
            description="numeric counts, non-percentage ratios, or probability figures",
        ),
        EntitySpec(
            slug="measurement",
            tag="METRIC",
            description="physical metrics, medical vitals, scientific results",
        ),
        EntitySpec(
            slug="value",
            tag="VALUE",
            description="numeric scores, ratings, ages, demographics, or spatial coordinates",
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
