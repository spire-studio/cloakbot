from __future__ import annotations

from cloakbot.privacy.core.types import GeneralEntity
from cloakbot.privacy.core.vault import _SessionMap
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.transparency.report import TurnReport, build_session_privacy_snapshot


def _entity(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)



def test_render_returns_empty_when_no_entities_were_masked() -> None:
    report = TurnReport(
        ctx=TurnContext(
            session_key="cli:test",
            turn_id="turn-1",
            raw_input="hello",
        )
    )

    rendered = report.render()

    assert "Privacy Report" in rendered
    assert "Intent: `chat`" in rendered
    assert "Newly detected this turn: _none_" in rendered
    assert "Tool-output detections: _none_" in rendered
    assert "Status: _no restoration needed_" in rendered



def test_render_summarizes_masked_entities() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="hello",
        was_sanitized=True,
        sanitized_input="Hello <<PERSON_1>> at <<EMAIL_1>>",
        sanitized_output="Nice to meet you, <<PERSON_1>>",
        user_input_entities=[
            _entity("Laurie Luo", "person"),
            _entity("alice@example.com", "email"),
        ],
    )

    rendered = TurnReport(ctx=ctx).render()

    assert "Privacy Report" in rendered
    assert "Input protection: _sanitized before remote LLM_" in rendered
    assert "`PERSON` x1 (`<<PERSON_1>>`)" in rendered
    assert "`EMAIL` x1 (`<<EMAIL_1>>`)" in rendered
    assert "Newly detected this turn: `EMAIL` (high) x1, `PERSON` (high) x1" in rendered
    assert "Restored in final output: `PERSON` x1 (`<<PERSON_1>>`)" in rendered


def test_build_session_privacy_snapshot_aggregates_vault_entities(monkeypatch) -> None:
    smap = _SessionMap()
    person, _ = smap.get_or_create_placeholder("Laurie Luo", "PERSON", turn_id="turn-1")
    smap.register_alias(person, "@laurie", turn_id="turn-2")
    email, _ = smap.get_or_create_placeholder("laurie@example.com", "EMAIL", turn_id="turn-1")

    monkeypatch.setattr(
        "cloakbot.privacy.transparency.report.get_map",
        lambda _session_key: smap,
    )

    snapshot = build_session_privacy_snapshot("webui:test")

    assert snapshot.total_entities == 2
    assert snapshot.entity_counts[0].entity_type == "EMAIL"
    assert snapshot.entity_counts[1].entity_type == "PERSON"
    by_placeholder = {entity.placeholder: entity for entity in snapshot.entities}
    assert by_placeholder[person].canonical == "Laurie Luo"
    assert by_placeholder[person].aliases == ["Laurie Luo", "@laurie"]
    assert by_placeholder[email].canonical == "laurie@example.com"
