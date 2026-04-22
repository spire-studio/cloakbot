from __future__ import annotations

from unittest.mock import patch

import pytest

from cloakbot.privacy.core.math.math_executor import (
    apply_privacy_math,
    build_math_execution_instruction,
)
from cloakbot.privacy.core.math.math_helpers import (
    execute_privacy_math,
    extract_python_snippet,
    extract_python_snippets,
)
from cloakbot.privacy.core.state.vault import _SessionMap


def test_build_instruction_contains_numeric_tokens() -> None:
    text = build_math_execution_instruction(
        "salary <<FINANCE_1>>, percentage <<PERCENTAGE_1>>, person <<PERSON_1>>"
    )
    assert "PRIVACY MODE ENABLED" in text
    assert "FINANCE_1" in text
    assert "PERCENTAGE_1" in text
    assert "PERCENTAGE_* are percent/share values" in text
    assert "PERSON_1" not in text


def test_extract_python_snippet() -> None:
    text = "answer\n<python_snippet_1>\nresult = (A + B) / C\n</python_snippet_1>"
    snippet = extract_python_snippet(text)
    assert snippet is not None
    assert "result =" in snippet


def test_execute_privacy_math() -> None:
    execution = execute_privacy_math("result = (A - B) / A", {"A": 100.0, "B": 60.0})
    assert execution.snippet_index == 1
    assert execution.expression == "(A - B) / A"
    assert abs(execution.result - 0.4) < 1e-12


@pytest.mark.asyncio
async def test_apply_privacy_math_replaces_snippet() -> None:
    text = (
        "Your margin is below.\n"
        "<python_snippet_1>\n"
        "result = AMOUNT_1 - AMOUNT_2\n"
        "</python_snippet_1>"
    )
    smap = _SessionMap(
        original_to_placeholder={"$100": "<<AMOUNT_1>>", "$60": "<<AMOUNT_2>>"},
        placeholder_to_original={"<<AMOUNT_1>>": "$100", "<<AMOUNT_2>>": "$60"},
        placeholder_to_value={"<<AMOUNT_1>>": 100, "<<AMOUNT_2>>": 60},
        counters={"AMOUNT": 2},
    )

    with patch("cloakbot.privacy.core.math.math_executor.get_map", return_value=smap):
        out = await apply_privacy_math(text, "cli:test")

    assert "python_snippet_1" not in out
    assert out == "Your margin is below.\n40"


def test_extract_python_snippets_multiple() -> None:
    text = (
        "<python_snippet_1>\nresult = A\n</python_snippet_1>\n"
        "<python_snippet_2>\nresult = B\n</python_snippet_2>"
    )
    assert extract_python_snippets(text) == [
        (1, "result = A"),
        (2, "result = B"),
    ]


@pytest.mark.asyncio
async def test_apply_privacy_math_executes_multiple_snippets() -> None:
    text = (
        "Scenario summaries.\n"
        "<python_snippet_1>\n"
        "result = FINANCE_1 * PERCENTAGE_1\n"
        "</python_snippet_1>\n"
        "<python_snippet_2>\n"
        "result = FINANCE_1 * PERCENTAGE_2\n"
        "</python_snippet_2>"
    )
    smap = _SessionMap(
        original_to_placeholder={
            "$100": "<<FINANCE_1>>",
            "10%": "<<PERCENTAGE_1>>",
            "20%": "<<PERCENTAGE_2>>",
        },
        placeholder_to_original={
            "<<FINANCE_1>>": "$100",
            "<<PERCENTAGE_1>>": "10%",
            "<<PERCENTAGE_2>>": "20%",
        },
        placeholder_to_value={
            "<<FINANCE_1>>": 100,
            "<<PERCENTAGE_1>>": 0.1,
            "<<PERCENTAGE_2>>": 0.2,
        },
        counters={"FINANCE": 1, "PERCENTAGE": 2},
    )

    with patch("cloakbot.privacy.core.math.math_executor.get_map", return_value=smap):
        out = await apply_privacy_math(text, "cli:test")

    assert "python_snippet_1" not in out
    assert "python_snippet_2" not in out
    assert out == "Scenario summaries.\n10\n20"
