from __future__ import annotations

import re
from loguru import logger
from cloakbot.privacy.core.math_helpers import (
    execute_privacy_math,
    extract_python_snippets,
    format_result,
    resolve_expression,
)
from cloakbot.privacy.core.vault import get_map
from cloakbot.privacy.core.types import REGISTRY

_PLACEHOLDER_RE = re.compile(r"^<<([A-Z]+(?:_[A-Z]+)*_\d+)>>$")
_INPUT_TOKEN_RE = re.compile(r"<<([A-Z]+(?:_[A-Z]+)*_\d+)>>")


def build_math_execution_instruction(sanitized_text: str) -> str:
    """Build detailed instructions for the remote LLM."""
    # Note: we only extract tokens that are actually present in the current sanitized text
    token_names = _extract_numeric_token_names(sanitized_text)

    lines = [
        "### PRIVACY MODE ENABLED ###",
        "You are working in a privacy-preserving environment. Follow these rules:",
        "1. RESTORATION: Tokens like <<FINANCE_1>> will be restored to their original values automatically. Treat them as opaque labels.",
        "2. COMPUTATION: If you need to show a calculated numeric result, emit a Python snippet block in this exact pattern:",
        "   '<python_snippet_N>result = FINANCE_1 * 0.1</python_snippet_N>'",
        "   Replace N with a positive integer such as 1, 2, 3, ...",
        "3. MULTIPLE CALCULATIONS: If your answer contains multiple independent calculations, emit multiple snippet blocks with increasing indices:",
        "   '<python_snippet_1>result = ...</python_snippet_1>'",
        "   '<python_snippet_2>result = ...</python_snippet_2>'",
        "4. OUTPUT BEHAVIOR: Each snippet block will be executed locally and replaced by its numeric result in the final output.",
        "5. For any numeric result derived from token values, do not compute or state the number directly in normal prose; emit a python_snippet block instead.",
        "6. If no calculation is needed, do not emit any python_snippet block.",
        "7. Token families have different semantics: FINANCE_* are money values, PERCENTAGE_* are percent/share values, and AMOUNT_* are counts or non-percentage ratios.",
        "",
        "Rules for python snippets:",
        "- Use only numeric token variables listed below.",
        "- ONLY remove angle brackets before using a token as a variable in python snippet: <<FINANCE_1>> -> FINANCE_1.",
        "- Each snippet must assign the final value to a variable named result.",
        "- Keep snippets minimal and arithmetic-only.",
        "- Do not include explanations, markdown, or extra text inside a snippet.",
        "- Do not nest snippets.",
        "- If you want to reuse the result of a already generated python snippet, repeat that whole snippet again. ",
    ]

    if token_names:
        lines.append("\nAvailable numeric token variables:")
        lines.extend(_describe_numeric_token(name) for name in token_names)

    return "\n".join(lines)


async def apply_privacy_math(response: str, session_key: str) -> str:
    """Execute snippets and replace them IN-PLACE with numeric results."""
    snippets = extract_python_snippets(response)
    if not snippets:
        return response

    smap = get_map(session_key)
    values = _build_variable_values(smap)

    final_text = response
    executions = []

    # Process each unique snippet index
    for snippet_index, snippet_content in snippets:
        try:
            execution = execute_privacy_math(snippet_content, values, snippet_index=snippet_index)
            executions.append(execution)

            # Replace the snippet tag with the result in the text
            target_re = re.compile(
                rf"<python_snippet_{snippet_index}>.*?</python_snippet_{snippet_index}>",
                re.DOTALL | re.IGNORECASE,
            )
            final_text = target_re.sub(format_result(execution.result), final_text)

        except Exception as e:
            logger.warning("math-executer: snippet {} failed: {}", snippet_index, e)
            # Cleanup tags on failure
            target_re = re.compile(
                rf"<python_snippet_{snippet_index}>(.*?)</python_snippet_{snippet_index}>",
                re.DOTALL | re.IGNORECASE,
            )
            final_text = target_re.sub(r"\1", final_text)

    # CRITICAL: We NO LONGER call replace_symbolic_variables here.
    # The final restoration stage in orchestrator.py will handle <<FINANCE_1>> -> $100,000 correctly.

    if not executions:
        return final_text

    # Append de-duplicated transparency report
    transparency = _render_transparency(executions, values)
    return f"{final_text.strip()}\n\n{transparency}"


def _extract_numeric_token_names(sanitized_text: str) -> list[str]:
    """Identify which tokens in the text are computable."""
    # Only allow tokens whose TAG belongs to the computable category in REGISTRY
    numeric_prefixes = tuple(REGISTRY.computable_tags)

    seen = set()
    names = []
    for match in _INPUT_TOKEN_RE.finditer(sanitized_text or ""):
        name = match.group(1)
        if name.startswith(numeric_prefixes):
            if name not in seen:
                seen.add(name)
                names.append(name)
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
    return f"- {name}"


def _build_variable_values(smap) -> dict[str, float]:
    """Build a simple map of token names to their numeric values."""
    values = {}
    for placeholder, val in smap.placeholder_to_value.items():
        match = _PLACEHOLDER_RE.fullmatch(placeholder)
        if match and isinstance(val, (int, float)):
            values[match.group(1)] = val
    return values


def _render_transparency(executions, values) -> str:
    """Render unique computation results for transparency."""
    # Deduplicate by expression to avoid repeating the same math 12 times
    unique_exprs = {}
    for ex in executions:
        resolved = resolve_expression(ex.expression, values)
        if resolved not in unique_exprs:
            unique_exprs[resolved] = ex.result

    if not unique_exprs:
        return ""

    if len(unique_exprs) == 1:
        expr, res = next(iter(unique_exprs.items()))
        return f"Local privacy computation (on-device): {expr} = {format_result(res)}."

    lines = ["Local privacy computations (on-device):"]
    for i, (expr, res) in enumerate(unique_exprs.items(), 1):
        lines.append(f" {i}. {expr} = {format_result(res)}.")
    return "\n".join(lines)
