from __future__ import annotations

import pytest

from cloakbot.privacy.core.math.math_helpers import (
    execute_privacy_math,
    extract_python_snippet,
    extract_python_snippets,
    remove_python_snippets,
)


def test_execute_privacy_math_simple_expression() -> None:
    execution = execute_privacy_math(
        "result = V1 + V2",
        {"V1": 2.0, "V2": 3.0},
    )

    assert execution.snippet_index == 1
    assert execution.expression == "V1 + V2"
    assert execution.result == 5.0


def test_execute_privacy_math_dos_guard_rejects_chained_exponentiation() -> None:
    with pytest.raises(ValueError, match="chained exponentiation is not allowed"):
        execute_privacy_math("result = V1 ** V2 ** V3", {"V1": 2.0, "V2": 3.0, "V3": 4.0})


def test_execute_privacy_math_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable/function: SECRET"):
        execute_privacy_math("result = V1 + SECRET", {"V1": 2.0})


def test_execute_privacy_math_rejects_non_numeric_result() -> None:
    with pytest.raises(ValueError, match="non-numeric result from math snippet"):
        execute_privacy_math("result = abs", {"V1": 1.0})


def test_extract_python_snippet_finds_snippet_between_tags() -> None:
    text = "answer\n<python_snippet_1>\nresult = V1 + V2\n</python_snippet_1>"

    snippet = extract_python_snippet(text)

    assert snippet == "result = V1 + V2"


def test_extract_python_snippet_returns_none_when_tags_absent() -> None:
    assert extract_python_snippet("result = V1 + V2") is None


def test_extract_python_snippets_finds_multiple_snippets_in_order() -> None:
    text = (
        "first\n"
        "<python_snippet_1>\nresult = V1 + V2\n</python_snippet_1>\n"
        "second\n"
        "<python_snippet_2>\nresult = V2 + V3\n</python_snippet_2>"
    )

    snippets = extract_python_snippets(text)

    assert snippets == [
        (1, "result = V1 + V2"),
        (2, "result = V2 + V3"),
    ]


def test_remove_python_snippets_removes_all_blocks() -> None:
    text = (
        "before\n"
        "<python_snippet_1>\nresult = V1 + V2\n</python_snippet_1>\n"
        "after"
    )

    cleaned = remove_python_snippets(text)

    assert "python_snippet_1" not in cleaned
    assert cleaned == "before\n\nafter"
