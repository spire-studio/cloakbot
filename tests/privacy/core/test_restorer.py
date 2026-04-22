from __future__ import annotations

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import (
    build_local_computation_annotations,
    restore_tokens,
    restore_tokens_with_annotations,
)
from cloakbot.privacy.core.state.vault import _SessionMap


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


def test_restore_tokens_with_annotations_returns_visible_restored_spans() -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="turn-1")
    smap.register_alias(placeholder, "@alice", turn_id="turn-2")

    restored, annotations = restore_tokens_with_annotations(
        f"Hello {placeholder}",
        smap,
    )

    assert restored == "Hello Alice Chen"
    assert len(annotations) == 1
    assert annotations[0].placeholder == placeholder
    assert annotations[0].text == "Alice Chen"
    assert annotations[0].start == 6
    assert annotations[0].end == 16
    assert annotations[0].entity_type == "person"
    assert annotations[0].aliases == ["Alice Chen", "@alice"]


def test_build_local_computation_annotations_marks_visible_result_span() -> None:
    annotations = build_local_computation_annotations(
        "The updated acquisition value is 252150000.",
        [
            LocalComputationRecord(
                snippet_index=1,
                expression="FINANCE_1 * 1.23",
                resolved_expression="205000000 * 1.23",
                result=252150000,
                formatted_result="252150000",
            )
        ],
    )

    assert len(annotations) == 1
    assert annotations[0].annotation_type == "local_computation"
    assert annotations[0].start == 33
    assert annotations[0].end == 42
    assert annotations[0].formula == "205000000 * 1.23"
