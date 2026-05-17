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
        "### MATH CONTRACT ###",
        "",
        "Tokens like <<FINANCE_1>>, <<PERCENTAGE_1>> are opaque variable names — they will be",
        "restored to real values locally. Do not try to guess what they represent.",
        "",
        "To produce a number from these tokens, EMBED a snippet INLINE in your prose,",
        "exactly where the number should appear. The snippet executes locally; its formatted",
        "result replaces the entire tag in the answer the user sees:",
        "",
        "    Her new balance is <python_snippet_1>result = FINANCE_1 * (1 + PERCENTAGE_1)</python_snippet_1>.",
        "",
        "RULES:",
        "1. EXACTLY ONE assignment per snippet: `result = <expression>`. No other statements.",
        "2. Inside the expression, use token names WITHOUT brackets: FINANCE_1, not <<FINANCE_1>>.",
        "3. To reuse an earlier snippet's result, reference it as CALC_N (N = prior index).",
        "4. Allowed: + - * / // % ** and functions abs, round, min, max, pow. Nothing else.",
        "5. PERCENTAGE_* (percent/share) is ALREADY a decimal fraction (0.04 for 4%). Use it",
        "   as a multiplier directly; do NOT divide by 100.",
        "6. NEVER write a computed number as bare text in your prose. EVERY numeric value the",
        "   user sees must come from a snippet — even simple echoes of an earlier CALC.",
        "7. NEVER stack snippets at the top of the response. Each snippet appears INLINE at",
        "   the exact position its result is needed in the prose.",
        "",
        "EXAMPLE (multi-step, inline):",
        "  User: What's my new portfolio value, and 4% of it for annual income?",
        "  You:  Your new portfolio is",
        "        <python_snippet_1>result = FINANCE_1 * (1 + PERCENTAGE_1)</python_snippet_1>.",
        "        At a 4% withdrawal rate, that's",
        "        <python_snippet_2>result = CALC_1 * PERCENTAGE_2</python_snippet_2> per year.",
        "",
        "ANTI-PATTERN (the exact failure this contract prevents — DO NOT do this):",
        "    <python_snippet_1>result = FINANCE_1 * (1 + PERCENTAGE_1)</python_snippet_1>",
        "    <python_snippet_2>result = CALC_1 * PERCENTAGE_2</python_snippet_2>",
        "    Her new balance is 909440. At a 4% rate, that's 36377.6 per year.",
        "  Snippets stacked at the top, then hardcoded numbers in prose. The 909440 and",
        "  36377.6 in the prose are dead literals — they leak verbatim to the user. EMBED",
        "  the snippets INLINE inside the prose instead.",
        "",
        "TOKEN SEMANTICS:",
        "  FINANCE_*    monetary amount",
        "  PERCENTAGE_* percent/share — decimal fraction, use as a multiplier",
        "  AMOUNT_*     count or non-percentage ratio",
        "  VALUE_*      generic numeric value (ages, counts, measurements)",
        "  METRIC_*     measurement (length, weight, etc.)",
        "  DATE_*       date/time — do NOT use in arithmetic",
        "  CALC_*       result of a prior snippet in this response",
    ]

    if token_names:
        lines.append("")
        lines.append("AVAILABLE TOKENS FOR THIS TURN:")
        lines.extend(_describe_numeric_token(name) for name in token_names)

    lines.append("")
    lines.append("If no calculation is needed, do not emit any snippet block.")

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
