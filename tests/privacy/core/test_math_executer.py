from __future__ import annotations

from unittest.mock import patch

import pytest

from cloakbot.privacy.core.math.math_executor import (
    apply_privacy_math,
    apply_privacy_math_for_turn,
    apply_privacy_math_with_details,
    build_math_execution_instruction,
)
from cloakbot.privacy.core.state.vault import _SessionMap


def test_build_math_execution_instruction_lists_numeric_tokens() -> None:
    instruction = build_math_execution_instruction(
        "Revenue is <<FINANCE_1>> and tax is <<PERCENTAGE_1>> for <<PERSON_1>>."
    )

    assert "PRIVACY MODE ENABLED" in instruction
    assert "FINANCE_1" in instruction
    assert "PERCENTAGE_1" in instruction
    assert "PERCENTAGE_* are percent/share values" in instruction
    assert "PERSON_1" not in instruction


def test_build_math_execution_instruction_lists_prior_calc_tokens(monkeypatch) -> None:
    smap = _SessionMap()
    smap.get_or_create_computation(
        expression="FINANCE_1 * 0.25",
        resolved_expression="100000 * 0.25",
        source_placeholders=["<<FINANCE_1>>"],
        value=25000,
        formatted_value="25000",
        turn_id="turn-1",
    )
    monkeypatch.setattr("cloakbot.privacy.core.math.math_executor.get_map", lambda _session_key: smap)

    instruction = build_math_execution_instruction("Use the prior result.", "cli:test")

    assert "CALC_1" in instruction
    assert "prior local calculation result" in instruction


@pytest.mark.asyncio
async def test_apply_privacy_math_executes_single_snippet() -> None:
    smap = _SessionMap(
        original_to_placeholder={
            "$100,000": "<<FINANCE_1>>",
            "10%": "<<PERCENTAGE_1>>",
        },
        placeholder_to_original={
            "<<FINANCE_1>>": "$100,000",
            "<<PERCENTAGE_1>>": "10%",
        },
        placeholder_to_value={
            "<<FINANCE_1>>": 100000,
            "<<PERCENTAGE_1>>": 0.1,
        },
        counters={"FINANCE": 1, "PERCENTAGE": 1},
    )
    response = (
        "Result below\n"
        "<python_snippet_1>\n"
        "result = FINANCE_1 * PERCENTAGE_1\n"
        "</python_snippet_1>"
    )

    with patch("cloakbot.privacy.core.math.math_executor.get_map", return_value=smap):
        output = await apply_privacy_math(response, "cli:test")

    assert "python_snippet_1" not in output
    assert output == "Result below\n10000"


@pytest.mark.asyncio
async def test_apply_privacy_math_skips_when_no_snippet() -> None:
    output = await apply_privacy_math("No computation", "cli:test")
    assert output == "No computation"


@pytest.mark.asyncio
async def test_apply_privacy_math_handles_failed_execution() -> None:
    smap = _SessionMap(
        original_to_placeholder={"$100,000": "<<AMOUNT_1>>"},
        placeholder_to_original={"<<AMOUNT_1>>": "$100,000"},
        placeholder_to_value={"<<AMOUNT_1>>": 100000},
        counters={"AMOUNT": 1},
    )
    response = (
        "Result below\n"
        "<python_snippet_1>\n"
        "result = UNKNOWN_1 + 1\n"
        "</python_snippet_1>"
    )

    with patch("cloakbot.privacy.core.math.math_executor.get_map", return_value=smap):
        output = await apply_privacy_math(response, "cli:test")

    # On failure, snippet tags are stripped but inner content is preserved
    assert "<python_snippet_1>" not in output
    assert "UNKNOWN_1 + 1" in output


@pytest.mark.asyncio
async def test_apply_privacy_math_with_details_returns_local_computation_records() -> None:
    smap = _SessionMap(
        original_to_placeholder={"$100,000": "<<FINANCE_1>>"},
        placeholder_to_original={"<<FINANCE_1>>": "$100,000"},
        placeholder_to_value={"<<FINANCE_1>>": 100000},
        counters={"FINANCE": 1},
    )
    response = (
        "Result below\n"
        "<python_snippet_1>\n"
        "result = FINANCE_1 * 0.25\n"
        "</python_snippet_1>"
    )

    with patch("cloakbot.privacy.core.math.math_executor.get_map", return_value=smap):
        output, records = await apply_privacy_math_with_details(response, "cli:test")

    assert output == "Result below\n25000"
    assert len(records) == 1
    assert records[0].resolved_expression == "100000 * 0.25"
    assert records[0].formatted_result == "25000"


@pytest.mark.asyncio
async def test_apply_privacy_math_persists_calc_placeholder(monkeypatch) -> None:
    smap = _SessionMap(
        original_to_placeholder={"$100,000": "<<FINANCE_1>>"},
        placeholder_to_original={"<<FINANCE_1>>": "$100,000"},
        placeholder_to_value={"<<FINANCE_1>>": 100000},
        counters={"FINANCE": 1},
    )
    saved: list[_SessionMap] = []
    response = (
        "Result below\n"
        "<python_snippet_1>\n"
        "result = FINANCE_1 * 0.25\n"
        "</python_snippet_1>"
    )

    monkeypatch.setattr("cloakbot.privacy.core.math.math_executor.get_map", lambda _session_key: smap)
    monkeypatch.setattr(
        "cloakbot.privacy.core.math.math_executor.save_map",
        lambda _session_key, saved_map: saved.append(saved_map),
    )

    result = await apply_privacy_math_for_turn(response, "cli:test", turn_id="turn-1")

    assert result.display_text == "Result below\n25000"
    assert "<<CALC_1>>" in result.remote_history_text
    assert "Local calculation result for python_snippet_1" in result.remote_history_text
    assert smap.placeholder_to_value["<<CALC_1>>"] == 25000
    assert smap.placeholder_to_computation["<<CALC_1>>"].expression == "FINANCE_1 * 0.25"
    assert saved == [smap]


@pytest.mark.asyncio
async def test_apply_privacy_math_reuses_existing_calc_placeholder(monkeypatch) -> None:
    smap = _SessionMap(
        original_to_placeholder={"$100,000": "<<FINANCE_1>>"},
        placeholder_to_original={"<<FINANCE_1>>": "$100,000"},
        placeholder_to_value={"<<FINANCE_1>>": 100000},
        counters={"FINANCE": 1},
    )
    computation, _ = smap.get_or_create_computation(
        expression="FINANCE_1 * 0.25",
        resolved_expression="100000 * 0.25",
        source_placeholders=["<<FINANCE_1>>"],
        value=25000,
        formatted_value="25000",
        turn_id="turn-1",
    )
    response = (
        "Result below\n"
        "<python_snippet_1>\n"
        "result = FINANCE_1 * 0.25\n"
        "</python_snippet_1>"
    )
    save_calls: list[_SessionMap] = []

    monkeypatch.setattr("cloakbot.privacy.core.math.math_executor.get_map", lambda _session_key: smap)
    monkeypatch.setattr(
        "cloakbot.privacy.core.math.math_executor.save_map",
        lambda _session_key, saved_map: save_calls.append(saved_map),
    )
    monkeypatch.setattr(
        "cloakbot.privacy.core.math.math_executor.execute_privacy_math",
        lambda *_args, **_kwargs: pytest.fail("existing CALC expression should skip execution"),
    )

    result = await apply_privacy_math_for_turn(response, "cli:test", turn_id="turn-2")

    assert result.display_text == "Result below\n25000"
    assert computation.placeholder in result.remote_history_text
    assert smap.counters["CALC"] == 1
    assert save_calls == []


@pytest.mark.asyncio
async def test_apply_privacy_math_skips_execution_when_calc_marker_exists(monkeypatch) -> None:
    smap = _SessionMap(
        original_to_placeholder={"$100,000": "<<FINANCE_1>>"},
        placeholder_to_original={"<<FINANCE_1>>": "$100,000"},
        placeholder_to_value={"<<FINANCE_1>>": 100000},
        counters={"FINANCE": 1},
    )
    computation, _ = smap.get_or_create_computation(
        expression="FINANCE_1 * 0.25",
        resolved_expression="100000 * 0.25",
        source_placeholders=["<<FINANCE_1>>"],
        value=25000,
        formatted_value="25000",
        turn_id="turn-1",
    )
    response = (
        "Result below\n"
        "<python_snippet_1>\n"
        "result = FINANCE_1 * 0.25\n"
        "</python_snippet_1>\n\n"
        f"Local calculation result for python_snippet_1: {computation.placeholder}. "
        "Use CALC_1 as the numeric variable for this prior local calculation in future python snippets."
    )

    monkeypatch.setattr("cloakbot.privacy.core.math.math_executor.get_map", lambda _session_key: smap)
    monkeypatch.setattr(
        "cloakbot.privacy.core.math.math_executor.execute_privacy_math",
        lambda *_args, **_kwargs: pytest.fail("existing CALC marker should skip execution"),
    )

    result = await apply_privacy_math_for_turn(response, "cli:test", turn_id="turn-2")

    assert result.display_text == "Result below\n25000"
    assert result.remote_history_text == response
