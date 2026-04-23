from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from cloakbot.privacy.core.types import DetectedEntity, REGISTRY, Severity
from cloakbot.privacy.core.state.vault import PLACEHOLDER_RE, get_map
from cloakbot.privacy.hooks.context import TurnContext


class EntitySummary(BaseModel):
    entity_type: str
    severity: Severity
    count: int


class PlaceholderSummary(BaseModel):
    tag: str
    count: int
    placeholders: list[str] = Field(default_factory=list)


class PrivacyReportData(BaseModel):
    intent: str
    input_was_sanitized: bool
    input_placeholders: list[PlaceholderSummary] = Field(default_factory=list)
    detected_input_entities: list[EntitySummary] = Field(default_factory=list)
    tool_output_entities: list[EntitySummary] = Field(default_factory=list)
    restored_output_placeholders: list[PlaceholderSummary] = Field(default_factory=list)


class SessionEntityData(BaseModel):
    placeholder: str
    entity_type: str
    severity: Severity
    canonical: str
    aliases: list[str] = Field(default_factory=list)
    value: int | float | str | None = None
    created_turn: str | None = None
    last_seen_turn: str | None = None


class SessionPrivacySnapshot(BaseModel):
    total_entities: int
    entities: list[SessionEntityData] = Field(default_factory=list)
    entity_counts: list[EntitySummary] = Field(default_factory=list)


class TurnReport(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ctx: TurnContext

    def build(self) -> PrivacyReportData:
        return PrivacyReportData(
            intent=self.ctx.intent.value,
            input_was_sanitized=self.ctx.was_sanitized,
            input_placeholders=_summarize_placeholders(self.ctx.sanitized_input),
            detected_input_entities=_summarize_entities(self.ctx.user_input_entities),
            tool_output_entities=_summarize_entities(self.ctx.tool_output_entities),
            restored_output_placeholders=_summarize_placeholders(self.ctx.sanitized_output),
        )

    def render(self) -> str:
        data = self.build()
        lines = ["### 🔒 Privacy Report  "]

        lines.append(f"├─ Intent: `{data.intent}`  ")

        if data.input_placeholders:
            status = "sanitized before remote LLM"
            if not data.input_was_sanitized:
                status = "placeholder-preserving input"
            lines.append(f"├─ Input protection: _{status}_  ")
            lines.append(f"│  > {_format_placeholder_summaries(data.input_placeholders)}  ")
        else:
            lines.append("├─ Input protection: _no placeholders sent to the remote LLM_  ")

        if data.detected_input_entities:
            lines.append(
                f"├─ Newly detected this turn: {_format_entity_summaries(data.detected_input_entities)}  "
            )
        else:
            lines.append("├─ Newly detected this turn: _none_  ")

        if data.tool_output_entities:
            lines.append(
                f"├─ Tool-output detections: {_format_entity_summaries(data.tool_output_entities)}  "
            )
        else:
            lines.append("├─ Tool-output detections: _none_  ")

        if data.restored_output_placeholders:
            lines.append(
                f"├─ Restored in final output: {_format_placeholder_summaries(data.restored_output_placeholders)}  "
            )
            lines.append("└─ Status: _tokens restored for display_")
        else:
            status = "_no restoration needed_" if not data.input_placeholders else "_nothing restored in final output_"
            lines.append(f"└─ Status: {status}")

        return "\n".join(lines)


def build_session_privacy_snapshot(session_key: str) -> SessionPrivacySnapshot:
    smap = get_map(session_key)
    entities = [
        SessionEntityData(
            placeholder=entity.placeholder,
            entity_type=entity.entity_type,
            severity=REGISTRY.severity_map.get(entity.entity_type, Severity.MEDIUM),
            canonical=entity.canonical,
            aliases=list(entity.aliases),
            value=entity.value,
            created_turn=entity.created_turn,
            last_seen_turn=entity.last_seen_turn,
        )
        for entity in sorted(
            smap.placeholder_to_entity.values(),
            key=lambda entity: (
                entity.created_turn or "",
                entity.last_seen_turn or "",
                entity.placeholder,
            ),
        )
    ]

    counts: Counter[tuple[str, Severity]] = Counter(
        (entity.entity_type.upper(), entity.severity) for entity in entities
    )
    entity_counts = [
        EntitySummary(entity_type=entity_type, severity=severity, count=count)
        for (entity_type, severity), count in sorted(counts.items())
    ]

    return SessionPrivacySnapshot(
        total_entities=len(entities),
        entities=entities,
        entity_counts=entity_counts,
    )


def _summarize_entities(entities: list[DetectedEntity]) -> list[EntitySummary]:
    counts: Counter[tuple[str, Severity]] = Counter(
        (entity.entity_type.upper(), entity.severity) for entity in entities
    )
    return [
        EntitySummary(entity_type=entity_type, severity=severity, count=count)
        for (entity_type, severity), count in sorted(counts.items())
    ]


def _summarize_placeholders(text: str) -> list[PlaceholderSummary]:
    counts: dict[str, list[str]] = {}
    for match in PLACEHOLDER_RE.finditer(text or ""):
        placeholder = match.group(0)
        tag, _index = placeholder[2:-2].rsplit("_", 1)
        counts.setdefault(tag, [])
        if placeholder not in counts[tag]:
            counts[tag].append(placeholder)

    return [
        PlaceholderSummary(tag=tag, count=len(placeholders), placeholders=placeholders)
        for tag, placeholders in sorted(counts.items())
    ]


def _format_entity_summaries(summaries: list[EntitySummary]) -> str:
    return ", ".join(
        f"`{summary.entity_type}` ({summary.severity.value}) x{summary.count}"
        for summary in summaries
    )


def _format_placeholder_summaries(summaries: list[PlaceholderSummary]) -> str:
    return ", ".join(
        f"`{summary.tag}` x{summary.count} ({', '.join(f'`{placeholder}`' for placeholder in summary.placeholders)})"
        for summary in summaries
    )
