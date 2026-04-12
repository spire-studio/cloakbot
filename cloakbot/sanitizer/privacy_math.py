"""
Privacy math runtime helpers.

- Build remote prompt augmentation from a local MathPlan.
- Extract python snippet from remote output.
- Execute arithmetic locally with a restricted evaluator.
- Apply deterministic post-processing (no heavy rewrite).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from cloakbot.sanitizer.pii_detector import MathPlan

_SNIPPET_RE = re.compile(
    r"<python_snippet_1>\s*(.*?)\s*</python_snippet_1>",
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
    expression: str
    result: float


def has_privacy_math(plan: MathPlan | None) -> bool:
    return bool(plan and plan.enabled)


def build_privacy_math_instruction(plan: MathPlan) -> str:
    """
    Build extra instruction for the remote LLM.

    Remote model receives semantic variable names only (never raw private values).
    """
    lines = [
        "PRIVACY_MATH_MODE:",
        "If the task requires arithmetic, include exactly one code block using these exact tags:",
        "<python_snippet_1>",
        "result = <expression>",
        "</python_snippet_1>",
        "Rules:",
        "- Use only listed variable names and numeric constants.",
        "- Do not assign concrete private values to variables.",
        "- Keep snippet minimal; arithmetic only.",
        "- Outside snippet, explain assumptions briefly.",
    ]
    if plan.intent:
        lines.append(f"- Task intent: {plan.intent}")
    lines.append("Available variables:")
    for var in plan.variables:
        desc = var.description.strip() or var.source_text.strip() or var.name
        lines.append(f"- {var.name}: {desc}")
    return "\n".join(lines)


def extract_python_snippet(text: str) -> str | None:
    match = _SNIPPET_RE.search(text or "")
    if not match:
        return None
    snippet = match.group(1).strip()
    return snippet or None


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


def execute_privacy_math(snippet: str, plan: MathPlan) -> MathExecution:
    values = {var.name: var.value for var in plan.variables}
    expr_text = _extract_expression(snippet)
    expr = ast.parse(expr_text, mode="eval")
    _validate_expression(expr, set(values.keys()))
    safe_locals = dict(values)
    safe_locals.update(_SAFE_FUNCS)
    result = eval(compile(expr, "<privacy_math>", "eval"), {"__builtins__": {}}, safe_locals)  # noqa: S307
    if isinstance(result, bool):
        raise ValueError("boolean result is not a valid numeric output")
    if not isinstance(result, (int, float)):
        raise ValueError("non-numeric result from math snippet")
    return MathExecution(expression=expr_text, result=float(result))


def _format_result(value: float) -> str:
    if abs(value - round(value)) < 1e-12:
        return str(int(round(value)))
    return f"{value:.10g}"


def _display_value(var_name: str, plan: MathPlan) -> str:
    for var in plan.variables:
        if var.name == var_name:
            source = var.source_text.strip()
            if source:
                return source
            return _format_result(var.value)
    return var_name


def _display_meaning(var_name: str, plan: MathPlan) -> str:
    for var in plan.variables:
        if var.name != var_name:
            continue
        desc = var.description.strip()
        value = _display_value(var_name, plan)
        if desc:
            if value and value not in desc:
                return f"{desc} ({value})"
            return desc
        return value
    return var_name


def _replace_symbolic_variables(text: str, plan: MathPlan) -> str:
    result = text
    names = sorted((v.name for v in plan.variables), key=len, reverse=True)
    for name in names:
        value_text = _display_value(name, plan)
        result = re.sub(rf"\\text\{{\s*{re.escape(name)}\s*\}}", value_text, result)
        result = re.sub(rf"\b{re.escape(name)}\b", value_text, result)
    return result.replace("%%", "%")


def _expression_with_values(expression: str, plan: MathPlan) -> str:
    result = expression
    names = sorted((v.name for v in plan.variables), key=len, reverse=True)
    for name in names:
        value = _display_value(name, plan)
        if value.endswith("%"):
            value = value[:-1]
        value = value.replace(",", "")
        result = re.sub(rf"\b{re.escape(name)}\b", value, result)
    return result


def _contains_symbolic_variables(text: str, plan: MathPlan) -> bool:
    for var in plan.variables:
        if re.search(rf"\b{re.escape(var.name)}\b", text):
            return True
        if re.search(rf"\\text\{{\s*{re.escape(var.name)}\s*\}}", text):
            return True
    return False


def _light_touch_cleanup(text: str) -> str:
    cleaned = text.replace("\r\n", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def apply_privacy_math(text: str, plan: MathPlan | None) -> str:
    """
    Resolve remote python snippet with local values and return polished text.
    """
    if not has_privacy_math(plan):
        return text

    snippet = extract_python_snippet(text)
    if not snippet:
        return text

    base_text = _SNIPPET_RE.sub("", text).strip()
    try:
        execution = execute_privacy_math(snippet, plan)
    except Exception as exc:
        logger.warning("privacy-math: failed to execute snippet locally: {}", exc)
        readable_base = _replace_symbolic_variables(base_text, plan)
        if base_text:
            return (
                f"{readable_base}\n\n"
                "(Detected a formula snippet, but local computation failed. Please verify the formula.)"
            )
        return "(Detected a formula snippet, but local computation failed. Please verify the formula.)"

    mapping = "; ".join(_display_meaning(var.name, plan) for var in plan.variables)
    resolved_expr = _expression_with_values(execution.expression, plan)
    transparency = (
        f"Local privacy computation (on-device): {resolved_expr} = {_format_result(execution.result)}.\n"
        f"Variable context: {mapping}\n"
        "Note: private values were computed locally; the remote model only returned a symbolic formula."
    )
    readable_base = _replace_symbolic_variables(base_text, plan)
    draft = f"{readable_base}\n\n{transparency}" if readable_base else transparency
    result = _light_touch_cleanup(draft)
    result = _replace_symbolic_variables(result, plan)
    if _contains_symbolic_variables(result, plan):
        result = _replace_symbolic_variables(result, plan)
    if "local" not in result.lower():
        result = f"{result}\n\n{transparency}"
    return result.strip()
