"""Low-level helpers for parsing and executing privacy math snippets."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

_SNIPPET_RE = re.compile(
    r"<python_snippet_(\d+)>\s*(.*?)\s*</python_snippet_\1>",
    flags=re.DOTALL | re.IGNORECASE,
)

_SAFE_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
}

_SAFE_NODE_TYPES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Call,
)


@dataclass
class MathExecution:
    snippet_index: int
    expression: str
    result: float


def extract_python_snippets(text: str) -> list[tuple[int, str]]:
    snippets: list[tuple[int, str]] = []
    for match in _SNIPPET_RE.finditer(text or ""):
        snippet_index = int(match.group(1))
        snippet = match.group(2).strip()
        if snippet:
            snippets.append((snippet_index, snippet))
    return snippets


def extract_python_snippet(text: str) -> str | None:
    snippets = extract_python_snippets(text)
    if not snippets:
        return None
    return snippets[0][1]


def remove_python_snippets(text: str) -> str:
    return _light_touch_cleanup(_SNIPPET_RE.sub("", text or ""))


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = re.sub(r"^```(?:python)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _validate_expression(expr: ast.AST, allowed_names: set[str]) -> None:
    for node in ast.walk(expr):
        if not isinstance(node, _SAFE_NODE_TYPES):
            raise ValueError(f"unsupported syntax in math snippet: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id not in allowed_names and node.id not in _SAFE_FUNCS:
                raise ValueError(f"unknown variable/function: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
                raise ValueError("only safe built-in math functions are allowed")


def _extract_expression(snippet: str) -> str:
    code = _strip_code_fence(snippet)
    module = ast.parse(code, mode="exec")
    expression_node: ast.AST | None = None

    for stmt in module.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name) and target.id == "result":
                expression_node = stmt.value
                continue
            raise ValueError("only assignment to `result` is allowed")
        if isinstance(stmt, ast.Expr) and expression_node is None:
            expression_node = stmt.value
            continue
        raise ValueError("unsupported statement in snippet")

    if expression_node is None:
        raise ValueError("no expression found in snippet")
    return ast.unparse(expression_node)


def execute_privacy_math(
    snippet: str,
    variables: dict[str, float],
    *,
    snippet_index: int = 1,
) -> MathExecution:
    expr_text = _extract_expression(snippet)
    # Prevent exponential blowup from chained exponentiation.
    if expr_text.count("**") >= 2:
        raise ValueError("chained exponentiation is not allowed")

    expr = ast.parse(expr_text, mode="eval")
    _validate_expression(expr, set(variables.keys()))
    safe_locals = dict(variables)
    safe_locals.update(_SAFE_FUNCS)

    result = eval(compile(expr, "<privacy_math>", "eval"), {"__builtins__": {}}, safe_locals)  # noqa: S307
    if isinstance(result, bool):
        raise ValueError("boolean result is not a valid numeric output")
    if not isinstance(result, (int, float)):
        raise ValueError("non-numeric result from math snippet")

    return MathExecution(
        snippet_index=snippet_index,
        expression=expr_text,
        result=float(result),
    )


def format_result(value: float) -> str:
    if abs(value - round(value)) < 1e-12:
        return str(int(round(value)))
    return f"{value:.10g}"


def resolve_expression(expression: str, values: dict[str, float]) -> str:
    result = expression
    names = sorted(values.keys(), key=len, reverse=True)
    for name in names:
        result = re.sub(rf"\b{re.escape(name)}\b", format_result(values[name]), result)
    return result


def replace_symbolic_variables(text: str, display_values: dict[str, str]) -> str:
    result = text
    names = sorted(display_values.keys(), key=len, reverse=True)
    for name in names:
        result = re.sub(rf"\b{re.escape(name)}\b", display_values[name], result)
    return result


def _light_touch_cleanup(text: str) -> str:
    cleaned = text.replace("\r\n", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


__all__ = [
    "MathExecution",
    "execute_privacy_math",
    "extract_python_snippet",
    "extract_python_snippets",
    "format_result",
    "remove_python_snippets",
    "replace_symbolic_variables",
    "resolve_expression",
]
