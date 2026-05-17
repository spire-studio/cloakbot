from __future__ import annotations

import re

from loguru import logger
from pydantic import BaseModel, Field

from cloakbot.privacy.core.math.math_helpers import (
    execute_privacy_math,
    extract_math_expression,
    extract_python_snippets,
    format_result,
    resolve_expression,
)
from cloakbot.privacy.core.state.vault import VaultComputation, _SessionMap, get_map, save_map
from cloakbot.privacy.core.types import REGISTRY

_PLACEHOLDER_RE = re.compile(r"^<<([A-Z]+(?:_[A-Z]+)*_\d+)>>$")
_INPUT_TOKEN_RE = re.compile(r"<<([A-Z]+(?:_[A-Z]+)*_\d+)>>")
_SNIPPET_BLOCK_RE = re.compile(
    r"<python_snippet_(\d+)>\s*(.*?)\s*</python_snippet_\1>",
    flags=re.DOTALL | re.IGNORECASE,
)
_CALC_MARKER_RE = re.compile(
    r"\s*Local calculation result for python_snippet_(\d+):\s*(<<CALC_\d+>>)\.\s*"
    r"Use CALC_\d+ as the numeric variable for this prior local calculation in future python snippets\.",
    flags=re.IGNORECASE,
)


class LocalComputationRecord(BaseModel):
    snippet_index: int
    expression: str
    resolved_expression: str
    result: float
    formatted_result: str
    placeholder: str | None = None
    source_placeholders: list[str] = Field(default_factory=list)


class PrivacyMathResult(BaseModel):
    display_text: str
    remote_history_text: str
    computations: list[LocalComputationRecord] = Field(default_factory=list)


def build_math_execution_instruction(sanitized_text: str, session_key: str | None = None) -> str:
    """Build detailed instructions for the remote LLM."""
    smap = get_map(session_key) if session_key is not None else None
    token_names = _extract_numeric_token_names(sanitized_text, smap)

    lines = [
        "### PRIVACY MODE ENABLED ###",
        "### PRIVACY MATH CONTRACT — STRICT — READ EVERY RULE ###",
        "",
        "Tokens like <<FINANCE_1>>, <<PERCENTAGE_1>>, <<VALUE_1>> are placeholders. They will be",
        "restored to real values locally — treat them as opaque variable names.",
        "",
        "If — and ONLY if — you need to produce a numeric result derived from those tokens, you",
        "MUST emit one or more Python snippet blocks following the contract below. Anything that",
        "looks like code but is NOT wrapped in the exact tag form will be shown to the user as raw",
        "text. That is the single most common failure mode of this contract — do not let it happen.",
        "",
        "─── 1. MANDATORY WRAPPER ─────────────────────────────────────────────",
        "Every computation MUST be wrapped in this EXACT form (N is a positive integer):",
        "    <python_snippet_N>result = <expression></python_snippet_N>",
        "Plain Python written outside this wrapper is NOT executed and WILL leak to the user as",
        "raw code.",
        "",
        "─── 2. ONE STATEMENT PER BLOCK ───────────────────────────────────────",
        "Each snippet block MUST contain EXACTLY ONE assignment: `result = <expression>`.",
        "Do NOT define intermediate variables inside a block (no `x = ...; result = x + 1`).",
        "Do NOT put multiple lines of code inside one block.",
        "",
        "─── 3. MULTI-STEP FORMULAS — DECOMPOSE AND CHAIN ─────────────────────",
        "If a formula needs multiple steps, emit MULTIPLE snippet blocks with INCREASING indices.",
        "To reuse a previous block's result, reference it as `CALC_N`, where N is the prior",
        "block's snippet index. Do NOT invent your own Python variable names like",
        "`contribution`, `rate`, `total`, `n`, `r` — those are unknown to the executor and the",
        "whole chain will fail.",
        "",
        "─── 4. ALLOWED IDENTIFIERS INSIDE AN EXPRESSION ──────────────────────",
        "  • Token names from the list at the bottom of this contract (strip the angle brackets:",
        "    use FINANCE_1, NOT <<FINANCE_1>>).",
        "  • CALC_N references to results of earlier snippet blocks in this same response.",
        "  • Plain numeric literals (12, 100, 0.5) — only for known constants like '12 months'.",
        "  • Whitelisted functions: abs, round, min, max, pow.",
        "  • Arithmetic operators: + - * / // % **.",
        "Anything else — names, imports, attribute access, function calls — will be rejected.",
        "",
        "─── 5. EXAMPLES ──────────────────────────────────────────────────────",
        "",
        "GOOD — single step:",
        "    <python_snippet_1>result = FINANCE_1 * PERCENTAGE_1</python_snippet_1>",
        "",
        "GOOD — multi-step annuity future value (FV of monthly contributions, compounded monthly):",
        "    <python_snippet_1>result = FINANCE_1 * PERCENTAGE_2</python_snippet_1>",
        "    <python_snippet_2>result = PERCENTAGE_1 / 12</python_snippet_2>",
        "    <python_snippet_3>result = (VALUE_2 - VALUE_1) * 12</python_snippet_3>",
        "    <python_snippet_4>result = CALC_1 * ((1 + CALC_2) ** CALC_3 - 1) / CALC_2</python_snippet_4>",
        "",
        "─── 6. ANTI-PATTERNS — NEVER EMIT ANY OF THESE ───────────────────────",
        "",
        "WRONG — no wrapper tag (this is shown verbatim to the user; this exact failure has",
        "happened in production):",
        "    contribution = FINANCE_1 * PERCENTAGE_2",
        "    r = PERCENTAGE_1 / 12",
        "    result = contribution * r",
        "",
        "WRONG — multiple statements inside one block (executor rejects the whole block):",
        "    <python_snippet_1>",
        "    contribution = FINANCE_1 * PERCENTAGE_2",
        "    result = contribution * 12",
        "    </python_snippet_1>",
        "",
        "WRONG — your own variable name referenced across blocks (executor cannot resolve",
        "`contribution`; you must use CALC_1 instead):",
        "    <python_snippet_1>result = FINANCE_1 * PERCENTAGE_2</python_snippet_1>",
        "    <python_snippet_2>result = contribution * 12</python_snippet_2>",
        "",
        "WRONG — bare token names in your prose answer (the EXACT failure this contract was",
        "rewritten to prevent; user sees the literal string `CALC_1` not the number):",
        "    Her updated balance is CALC_1, at a PERCENTAGE_2 rate per year of CALC_2.",
        "",
        "WRONG — literal arithmetic in prose (user sees `CALC_2 / 12` not the per-month figure):",
        "    Per month, that is CALC_2 / 12.",
        "",
        "─── 7. PROSE OUTPUT — REFERENCE VALUES WITH <<TOKEN>> BRACKETS ───────",
        "In your prose answer, refer to any value using the SAME bracket form the user input",
        "used: <<FINANCE_1>>, <<PERCENTAGE_2>>, <<CALC_1>>, etc. The restorer substitutes",
        "these back to the original user-visible values (e.g. <<PERCENTAGE_2>> → '4%',",
        "<<FINANCE_1>> → '$812,000').",
        "",
        "To reference a previously-computed snippet result in prose, use <<CALC_N>> with",
        "brackets — same pattern. The restorer substitutes it with the formatted number",
        "(e.g. <<CALC_1>> → '$909,440').",
        "",
        "NEVER drop the brackets in prose. A bare `CALC_1`, `PERCENTAGE_2`, or `FINANCE_3`",
        "in the answer text leaks to the user as the literal string — the restorer ONLY",
        "matches the bracketed form <<TOKEN_N>>.",
        "",
        "RIGHT — full answer for a balance + withdrawal example:",
        "    <python_snippet_1>result = FINANCE_1 * (1 + PERCENTAGE_1)</python_snippet_1>",
        "    <python_snippet_2>result = CALC_1 * PERCENTAGE_2</python_snippet_2>",
        "    Her new balance is <<CALC_1>>. At a <<PERCENTAGE_2>> withdrawal rate, that's",
        "    <<CALC_2>> per year.",
        "",
        "For NEW inline arithmetic that wasn't computed in an earlier snippet (e.g. dividing",
        "<<CALC_2>> by 12 for a monthly figure), emit a fresh snippet block — do NOT write",
        "literal arithmetic in the prose:",
        "    ... which is <python_snippet_3>result = CALC_2 / 12</python_snippet_3> per month.",
        "",
        "If the user's question requires NO calculation, do not emit any snippet block.",
        "Do not repeat prior executed snippets unless the user explicitly asks to recompute.",
        "",
        "─── 8. TOKEN SEMANTICS ───────────────────────────────────────────────",
        "  FINANCE_*    — monetary amount.",
        "  PERCENTAGE_* — percent/share, ALREADY normalized locally as a decimal fraction",
        "                 (so a 30% input becomes 0.30 inside the executor). Use directly as",
        "                 a multiplier; do NOT divide by 100.",
        "  AMOUNT_*     — count or non-percentage ratio.",
        "  VALUE_*      — generic numeric value (ages, counts, measurements when no more",
        "                 specific family applies).",
        "  METRIC_*     — measurement (length, weight, etc.).",
        "  DATE_*       — date/time. Do NOT use directly in arithmetic.",
        "  CALC_*       — result of a prior snippet in this response; reference it by name.",
    ]

    if token_names:
        lines.append("")
        lines.append("─── 9. AVAILABLE TOKEN VARIABLES FOR THIS TURN ───────────────────────")
        lines.extend(_describe_numeric_token(name) for name in token_names)

    lines.append("")
    lines.append("### END PRIVACY MATH CONTRACT ###")

    return "\n".join(lines)


async def apply_privacy_math(response: str, session_key: str) -> str:
    final_text, _records = await apply_privacy_math_with_details(response, session_key)
    return final_text


async def apply_privacy_math_with_details(
    response: str,
    session_key: str,
) -> tuple[str, list[LocalComputationRecord]]:
    result = await apply_privacy_math_for_turn(response, session_key)
    return result.display_text, result.computations


async def apply_privacy_math_for_turn(
    response: str,
    session_key: str,
    *,
    turn_id: str | None = None,
) -> PrivacyMathResult:
    """Execute new snippets locally and build separate display/history text."""
    if not extract_python_snippets(response):
        return PrivacyMathResult(display_text=response, remote_history_text=response)

    smap = get_map(session_key)
    values = _build_variable_values(smap)
    display_parts: list[str] = []
    history_parts: list[str] = []
    records: list[LocalComputationRecord] = []
    cursor = 0
    modified_vault = False

    for match in _SNIPPET_BLOCK_RE.finditer(response or ""):
        snippet_index = int(match.group(1))
        snippet_content = match.group(2).strip()
        marker = _read_existing_calc_marker(response, match.end(), snippet_index)
        marker_placeholder = marker[0] if marker is not None else None
        marker_end = marker[1] if marker is not None else match.end()

        display_parts.append(response[cursor:match.start()])
        history_parts.append(response[cursor:match.start()])

        try:
            computation, record, is_new = _resolve_or_execute_snippet(
                snippet_content,
                snippet_index,
                values,
                smap,
                marker_placeholder=marker_placeholder,
                turn_id=turn_id,
            )
            records.append(record)
            modified_vault = modified_vault or is_new
            display_parts.append(computation.formatted_value)
            history_parts.append(computation.placeholder)
            # Propagate the new CALC binding to the local `values` dict so a
            # later snippet in the SAME response can reference it (e.g. a
            # snippet that does `result = ... CALC_1 ...` immediately after
            # the snippet that produced CALC_1). Without this, the AST
            # validator below would reject CALC_1 as an unknown variable
            # because the smap update is not visible to the validator's
            # `allowed_names = set(values.keys())` snapshot taken per snippet.
            if computation.placeholder:
                placeholder_match = _PLACEHOLDER_RE.fullmatch(computation.placeholder)
                if placeholder_match is not None:
                    values[placeholder_match.group(1)] = float(computation.value)
        except Exception as exc:
            logger.warning("math-executer: snippet {} failed: {}", snippet_index, exc)
            display_parts.append(snippet_content)
            history_parts.append(snippet_content)

        cursor = marker_end

    display_parts.append(response[cursor:])
    history_parts.append(response[cursor:])

    if modified_vault:
        save_map(session_key, smap)

    return PrivacyMathResult(
        display_text=_clean_output("".join(display_parts)),
        remote_history_text=_clean_output("".join(history_parts)),
        computations=_deduplicate_records(records),
    )


def _resolve_or_execute_snippet(
    snippet_content: str,
    snippet_index: int,
    values: dict[str, float],
    smap: _SessionMap,
    *,
    marker_placeholder: str | None,
    turn_id: str | None,
) -> tuple[VaultComputation, LocalComputationRecord, bool]:
    existing = smap.get_computation(marker_placeholder) if marker_placeholder else None
    if existing is not None:
        existing.last_seen_turn = turn_id or existing.last_seen_turn
        return existing, _record_from_computation(snippet_index, existing), False

    expression = extract_math_expression(snippet_content)
    existing = smap.find_computation(expression)
    if existing is not None:
        existing.last_seen_turn = turn_id or existing.last_seen_turn
        return existing, _record_from_computation(snippet_index, existing), False

    execution = execute_privacy_math(snippet_content, values, snippet_index=snippet_index)
    resolved_expression = resolve_expression(execution.expression, values)
    source_placeholders = _extract_source_placeholders(execution.expression, values)
    computation, is_new = smap.get_or_create_computation(
        expression=execution.expression,
        resolved_expression=resolved_expression,
        source_placeholders=source_placeholders,
        value=execution.result,
        formatted_value=format_result(execution.result),
        turn_id=turn_id,
    )
    return computation, _record_from_computation(snippet_index, computation), is_new


def _record_from_computation(
    snippet_index: int,
    computation: VaultComputation,
) -> LocalComputationRecord:
    return LocalComputationRecord(
        snippet_index=snippet_index,
        expression=computation.expression,
        resolved_expression=computation.resolved_expression,
        result=computation.value,
        formatted_result=computation.formatted_value,
        placeholder=computation.placeholder,
        source_placeholders=computation.source_placeholders,
    )


def _extract_numeric_token_names(sanitized_text: str, smap: _SessionMap | None = None) -> list[str]:
    """Identify which tokens in the text are computable."""
    numeric_prefixes = tuple([*REGISTRY.computable_tags, "CALC"])

    seen: set[str] = set()
    names: list[str] = []
    for match in _INPUT_TOKEN_RE.finditer(sanitized_text or ""):
        name = match.group(1)
        if name.startswith(numeric_prefixes) and name not in seen:
            seen.add(name)
            names.append(name)

    if smap is not None:
        for placeholder in smap.placeholder_to_computation:
            match = _PLACEHOLDER_RE.fullmatch(placeholder)
            if match and match.group(1) not in seen:
                seen.add(match.group(1))
                names.append(match.group(1))
    return names


def _describe_numeric_token(name: str) -> str:
    """Render a short semantic hint for each numeric token family."""
    if name.startswith("FINANCE_"):
        return f"- {name}: monetary amount token"
    if name.startswith("PERCENTAGE_"):
        return (
            f"- {name}: percentage/share token normalized locally as a decimal fraction; "
            "use as a multiplier for the referenced base quantity"
        )
    if name.startswith("AMOUNT_"):
        return f"- {name}: count or non-percentage ratio token"
    if name.startswith("DATE_"):
        return f"- {name}: date/time token"
    if name.startswith("METRIC_"):
        return f"- {name}: measurement token"
    if name.startswith("VALUE_"):
        return f"- {name}: generic numeric value token"
    if name.startswith("CALC_"):
        return f"- {name}: prior local calculation result"
    return f"- {name}"


def _build_variable_values(smap: _SessionMap) -> dict[str, float]:
    """Build a simple map of token names to their numeric values."""
    values = {}
    for placeholder, val in smap.placeholder_to_value.items():
        match = _PLACEHOLDER_RE.fullmatch(placeholder)
        if match and isinstance(val, (int, float)):
            values[match.group(1)] = float(val)
    return values


def _extract_source_placeholders(expression: str, values: dict[str, float]) -> list[str]:
    names = sorted(values.keys(), key=len, reverse=True)
    return [f"<<{name}>>" for name in names if re.search(rf"\b{re.escape(name)}\b", expression)]


def _read_existing_calc_marker(
    text: str,
    start: int,
    snippet_index: int,
) -> tuple[str, int] | None:
    match = _CALC_MARKER_RE.match(text or "", start)
    if match is None or int(match.group(1)) != snippet_index:
        return None
    return match.group(2), match.end()


def _clean_output(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()


def _deduplicate_records(records: list[LocalComputationRecord]) -> list[LocalComputationRecord]:
    seen: set[str] = set()
    deduplicated: list[LocalComputationRecord] = []
    for record in records:
        if record.resolved_expression in seen:
            continue
        seen.add(record.resolved_expression)
        deduplicated.append(record)
    return deduplicated
