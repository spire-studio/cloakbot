from __future__ import annotations

from cloakbot.privacy.core.types import GeneralEntity
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.transparency.report import TurnReport


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

    assert report.render() == ""



def test_render_summarizes_masked_entities() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="hello",
        was_sanitized=True,
        user_input_entities=[
            _entity("Laurie Luo", "person"),
            _entity("alice@example.com", "email"),
        ],
    )

    rendered = TurnReport(ctx=ctx).render()

    assert "Privacy Report" in rendered
    assert "`PERSON` (high)" in rendered
    assert "`EMAIL` (high)" in rendered
    assert "all tokens restored" in rendered
