from __future__ import annotations

import json
import re
import time
from typing import Any

from loguru import logger

from cloakbot.providers.vllm import get_vllm_client, get_vllm_model


class JsonCompletionRunner:
    """Run a non-streaming local vLLM completion that must return JSON."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._temperature = temperature

    async def complete(self, system_prompt: str, prompt: str) -> tuple[str, float]:
        client = get_vllm_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        t0 = time.perf_counter()
        try:
            raw_output = await self._complete_once(client, messages)
            if not is_valid_json_object(raw_output):
                logger.warning("Local JSON model returned invalid JSON; retrying once")
                raw_output = await self._complete_once(client, messages)
        except Exception:
            logger.exception("Local JSON model call failed")
            raise

        latency_ms = (time.perf_counter() - t0) * 1000
        return raw_output, latency_ms

    async def _complete_once(
        self,
        client: Any,
        messages: list[dict[str, str]],
    ) -> str:
        response = await client.chat.completions.create(
            model=get_vllm_model(),
            messages=messages,  # type: ignore[arg-type]
            temperature=self._temperature,
            stream=False,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""


def strip_think_block(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_json(text: str) -> str:
    cleaned = strip_think_block(text)
    match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    return cleaned.strip()


def load_json_object(raw: str) -> dict[str, object]:
    json_text = extract_json(raw)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("Local JSON model returned invalid JSON; treating as empty object")
        return {}
    if not isinstance(data, dict):
        logger.warning("Local JSON model returned non-object JSON; treating as empty object")
        return {}
    return data


def is_valid_json_object(raw: str) -> bool:
    json_text = extract_json(raw)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict)


def parse_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return default


def parse_should_sanitize(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError(f"invalid should_sanitize value: {value!r}")


def parse_numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?\s*%?", value.strip())
        if not match:
            return None
        raw = match.group(0).replace(",", "").strip()
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def normalize_var_name(value: object, *, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]", "", str(value or "").strip())
    if not text:
        return fallback
    if text[0].isdigit():
        text = f"V_{text}"
    return text.upper()


def find_numeric_substring(prompt: str, value: float) -> str:
    pattern = r"[$¥€£]?\s*-?\d[\d,]*(?:\.\d+)?\s*%?"
    for match in re.finditer(pattern, prompt):
        token = match.group(0).strip()
        raw = token
        for symbol in ("$", "¥", "€", "£"):
            raw = raw.replace(symbol, "")
        raw = raw.replace(",", "").strip()
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        if not raw:
            continue
        try:
            parsed = float(raw)
        except ValueError:
            continue
        if abs(parsed - value) < 1e-9:
            return token
    return ""


__all__ = [
    "JsonCompletionRunner",
    "extract_json",
    "find_numeric_substring",
    "is_valid_json_object",
    "load_json_object",
    "normalize_var_name",
    "parse_bool",
    "parse_numeric",
    "parse_should_sanitize",
    "strip_think_block",
]
