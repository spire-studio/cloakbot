from __future__ import annotations

from cloakbot.privacy.core.restorer import restore_tokens
from cloakbot.privacy.core.vault import _SessionMap


def test_restore_tokens_reverses_person_token_to_original_value() -> None:
    smap = _SessionMap(
        original_to_placeholder={"Alice Chen": "<<PERSON_1>>"},
        placeholder_to_original={"<<PERSON_1>>": "Alice Chen"},
        counters={"PERSON": 1},
    )

    restored = restore_tokens("Hello <<PERSON_1>>", smap)

    assert restored == "Hello Alice Chen"



def test_restore_tokens_uses_longest_token_first() -> None:
    smap = _SessionMap(
        original_to_placeholder={},
        placeholder_to_original={
            "<<PERSON_1>>": "Alice",
            "<<PERSON_10>>": "Bob",
        },
        counters={"PERSON": 10},
    )

    restored = restore_tokens("<<PERSON_10>> and <<PERSON_1>>", smap)

    assert restored == "Bob and Alice"



def test_restore_tokens_returns_text_unchanged_when_no_tokens_present() -> None:
    smap = _SessionMap(
        original_to_placeholder={"Alice Chen": "<<PERSON_1>>"},
        placeholder_to_original={"<<PERSON_1>>": "Alice Chen"},
        counters={"PERSON": 1},
    )

    restored = restore_tokens("Nothing to restore here.", smap)

    assert restored == "Nothing to restore here."


def test_restore_tokens_ignores_bare_token_names() -> None:
    """Bare token names (without <<>>) should NOT be restored."""
    smap = _SessionMap(
        original_to_placeholder={"Alice Chen": "<<PERSON_1>>"},
        placeholder_to_original={"<<PERSON_1>>": "Alice Chen"},
        counters={"PERSON": 1},
    )

    restored = restore_tokens("Hello PERSON_1", smap)

    assert restored == "Hello PERSON_1"


def test_restore_tokens_handles_multiple_types() -> None:
    smap = _SessionMap(
        original_to_placeholder={},
        placeholder_to_original={
            "<<PERSON_1>>": "Alice",
            "<<EMAIL_1>>": "alice@example.com",
            "<<FINANCE_1>>": "$100,000",
        },
    )

    text = "<<PERSON_1>> earns <<FINANCE_1>>, contact <<EMAIL_1>>"
    restored = restore_tokens(text, smap)

    assert restored == "Alice earns $100,000, contact alice@example.com"


def test_restore_tokens_leaves_unknown_placeholders_intact() -> None:
    smap = _SessionMap(
        original_to_placeholder={},
        placeholder_to_original={"<<PERSON_1>>": "Alice"},
    )

    restored = restore_tokens("<<PERSON_1>> and <<PERSON_2>>", smap)

    assert restored == "Alice and <<PERSON_2>>"
