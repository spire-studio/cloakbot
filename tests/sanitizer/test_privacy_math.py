from __future__ import annotations

import pytest

from cloakbot.sanitizer.pii_detector import MathPlan, MathVariable
from cloakbot.sanitizer.privacy_math import (
    apply_privacy_math,
    build_privacy_math_instruction,
    execute_privacy_math,
    extract_python_snippet,
    has_privacy_math,
)


def _plan() -> MathPlan:
    return MathPlan(
        is_math_task=True,
        intent="calculate profit margin",
        variables=[
            MathVariable(
                name="V1",
                value=100.0,
                description="revenue",
                source_text="$100",
                is_sensitive=True,
            ),
            MathVariable(
                name="V2",
                value=60.0,
                description="cost",
                source_text="$60",
                is_sensitive=True,
            ),
        ],
    )


def test_has_privacy_math():
    assert has_privacy_math(_plan()) is True
    assert has_privacy_math(None) is False


def test_build_instruction_contains_variables():
    text = build_privacy_math_instruction(_plan())
    assert "PRIVACY_MATH_MODE" in text
    assert "V1" in text
    assert "V2" in text


def test_extract_python_snippet():
    text = "answer\n<python_snippet_1>\nresult = (V1 - V2) / V1\n</python_snippet_1>"
    snippet = extract_python_snippet(text)
    assert snippet is not None
    assert "result =" in snippet


def test_execute_privacy_math():
    execution = execute_privacy_math("result = (V1 - V2) / V1", _plan())
    assert execution.expression == "(V1 - V2) / V1"
    assert abs(execution.result - 0.4) < 1e-12


async def test_apply_privacy_math_replaces_snippet():
    text = (
        "Your margin is below.\n"
        "<python_snippet_1>\n"
        "result = (V1 - V2) / V1\n"
        "</python_snippet_1>"
    )
    out = await apply_privacy_math(text, _plan())
    assert "python_snippet_1" not in out
    assert "local" in out.lower()


@pytest.mark.asyncio
async def test_apply_privacy_math_replaces_symbolic_variables():
    text = (
        "Computed with V1 and V2. Formula: \\text{V1} * \\text{V2} / 100.\n"
        "<python_snippet_1>\n"
        "result = V1 * V2 / 100\n"
        "</python_snippet_1>"
    )
    out = await apply_privacy_math(text, _plan())
    assert "V1" not in out
    assert "V2" not in out
    assert "\\text{V1}" not in out
