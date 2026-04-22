from __future__ import annotations

from cloakbot.privacy.core.sanitization.handler import apply_tokens
from cloakbot.privacy.core.types import GeneralEntity, ComputableEntity, DetectionResult
from cloakbot.privacy.core.state.vault import _SessionMap


def _general(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


def _computable(text: str, entity_type: str, value: int | float | str) -> ComputableEntity:
    return ComputableEntity(text=text, entity_type=entity_type, value=value)


def _detection(prompt: str, entities: list) -> DetectionResult:
    return DetectionResult(
        original_prompt=prompt,
        entities=entities,
        llm_raw_output="",
        latency_ms=0.0,
    )


def _empty_map() -> _SessionMap:
    return _SessionMap(
        original_to_placeholder={},
        placeholder_to_original={},
    )


def test_apply_tokens_replaces_entities_with_angle_bracket_tokens() -> None:
    detection = _detection(
        "Alice alice@example.com",
        [
            _general("Alice", "person"),
            _general("alice@example.com", "email"),
        ],
    )

    text, modified = apply_tokens(detection, _empty_map())

    assert modified is True
    assert text == "<<PERSON_1>> <<EMAIL_1>>"


def test_apply_tokens_uses_longest_entity_first() -> None:
    detection = _detection(
        "张伟明和张伟",
        [
            _general("张伟", "person"),
            _general("张伟明", "person"),
        ],
    )

    text, modified = apply_tokens(detection, _empty_map())

    assert modified is True
    assert text == "<<PERSON_1>>和<<PERSON_2>>"
    assert "张伟明" not in text
    assert "张伟" not in text


def test_same_entity_in_two_turns_gets_same_token() -> None:
    smap = _empty_map()

    first_detection = _detection("Hello Alice", [_general("Alice", "person")])
    second_detection = _detection("Alice again", [_general("Alice", "person")])

    first_text, first_modified = apply_tokens(first_detection, smap)
    second_text, second_modified = apply_tokens(second_detection, smap)

    assert first_modified is True
    assert second_modified is True
    assert first_text == "Hello <<PERSON_1>>"
    assert second_text == "<<PERSON_1>> again"
    assert smap.counters["PERSON"] == 1


def test_apply_tokens_returns_unmodified_when_no_sensitive_entities() -> None:
    detection = _detection("What is the capital of France?", [])

    text, modified = apply_tokens(detection, _empty_map())

    assert modified is False
    assert text == "What is the capital of France?"


def test_apply_tokens_skips_placeholder_like_entities() -> None:
    smap = _empty_map()
    detection = _detection(
        "Hello <<PERSON_1>>",
        [_general("<<PERSON_1>>", "person")],
    )

    text, modified = apply_tokens(detection, smap)

    assert modified is False
    assert text == "Hello <<PERSON_1>>"
    assert smap.original_to_placeholder == {}


def test_apply_tokens_skips_entities_containing_existing_tokens() -> None:
    smap = _empty_map()
    detection = _detection(
        "Amount is $<<AMOUNT_1>>",
        [_general("$<<AMOUNT_1>>", "financial")],
    )

    text, modified = apply_tokens(detection, smap)

    assert modified is False
    assert text == "Amount is $<<AMOUNT_1>>"


def test_apply_tokens_does_not_corrupt_existing_placeholders() -> None:
    """Core regression test: entity "1" must not corrupt <<PERSON_1>>."""
    smap = _empty_map()
    smap.original_to_placeholder["Alice Chen"] = "<<PERSON_1>>"
    smap.placeholder_to_original["<<PERSON_1>>"] = "Alice Chen"
    smap.counters["PERSON"] = 1

    detection = _detection(
        "Your name is <<PERSON_1>>.",
        [_computable("1", "computable_other", 1)],
    )

    text, modified = apply_tokens(detection, smap)

    # "1" only appears inside <<PERSON_1>> — must be skipped
    assert modified is False
    assert text == "Your name is <<PERSON_1>>."


def test_apply_tokens_replaces_entity_outside_placeholder_but_skips_inside() -> None:
    """If "1" appears both inside a placeholder AND as standalone, only standalone is replaced."""
    smap = _empty_map()
    smap.original_to_placeholder["Alice"] = "<<PERSON_1>>"
    smap.placeholder_to_original["<<PERSON_1>>"] = "Alice"
    smap.counters["PERSON"] = 1

    detection = _detection(
        "<<PERSON_1>> has 1 cat",
        [_computable("1", "amount", 1)],
    )

    text, modified = apply_tokens(detection, smap)

    assert modified is True
    assert "<<PERSON_1>>" in text  # Not corrupted
    assert "<<AMOUNT_1>>" in text  # Standalone "1" was replaced
    assert text == "<<PERSON_1>> has <<AMOUNT_1>> cat"


def test_apply_tokens_stores_computable_value_in_vault() -> None:
    smap = _empty_map()
    detection = _detection(
        "salary $100,000",
        [_computable("$100,000", "financial", 100000)],
    )

    apply_tokens(detection, smap)

    assert smap.placeholder_to_value["<<FINANCE_1>>"] == 100000


def test_apply_tokens_uses_percentage_placeholder_tag() -> None:
    smap = _empty_map()
    detection = _detection(
        "bonus rate 10%",
        [_computable("10%", "percentage", 0.1)],
    )

    text, modified = apply_tokens(detection, smap)

    assert modified is True
    assert text == "bonus rate <<PERCENTAGE_1>>"
    assert smap.placeholder_to_value["<<PERCENTAGE_1>>"] == 0.1
