#!/usr/bin/env python
"""Live smoke test for the local privacy detector endpoint.

Exercises the REAL production detector path (PydanticAI + ``NativeOutput``)
against the Gemma endpoint configured in ``config.privacy``, and gives a
definitive verdict on whether the server honours JSON-Schema structured output
— the thing ``NativeOutput`` requires. The unit suite uses fake models and
cannot catch a server that doesn't support schema-constrained decoding; this
script can.

Run:
    uv run python scripts/privacy_detector_smoke.py

It sends only SYNTHETIC sample PII to the LOCAL endpoint (never your real data),
and nothing leaves the configured local host — that is the privacy boundary the
detector is designed around.

Exit code 0 = all checks passed; non-zero = something needs attention.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


OK = _c("32", "[PASS]")
NO = _c("31", "[FAIL]")
WARN = _c("33", "[WARN]")
DOT = "  ·"


def _section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def _quiet_logs() -> None:
    """Silence the detectors' DEBUG chatter so the report stays readable."""
    try:
        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
    except Exception:
        pass


async def main() -> int:
    _quiet_logs()
    failures = 0
    native_ok = False

    # ------------------------------------------------------------------ 1
    _section("1. Detector endpoint configuration")
    try:
        from cloakbot.providers.detector import get_detector_client, get_detector_model

        client = get_detector_client()  # raises if privacy is not configured
        model_name = get_detector_model()
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"{NO} privacy detector is not configured: {exc}")
        print("    Run `cloakbot onboard` -> [D] Privacy Detector, or set it in")
        print("    the WebUI Settings -> Privacy tab, then re-run this script.")
        return 1

    base_url = str(getattr(client, "base_url", "?"))
    api_key = getattr(client, "api_key", "") or ""
    masked = f"{api_key[:4]}…" if api_key else "(none)"
    print(f"{OK} configured")
    print(f"{DOT} base_url : {base_url}")
    print(f"{DOT} model    : {model_name}")
    print(f"{DOT} api_key  : {masked}")
    if base_url and not any(h in base_url for h in ("127.0.0.1", "localhost", "0.0.0.0", "::1")):
        print(f"{WARN} base_url is not loopback — the detector sees RAW input, so a remote")
        print("       host breaks the privacy boundary. Keep this endpoint LOCAL.")

    # ------------------------------------------------------------------ 2
    _section("2. Connectivity (plain completion)")
    try:
        t0 = time.perf_counter()
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Reply with the single word: pong"}],
            temperature=0.0,
            stream=False,
        )
        dt = (time.perf_counter() - t0) * 1000
        text = (resp.choices[0].message.content or "").strip()
        print(f"{OK} endpoint reachable ({dt:.0f} ms) — model said: {text[:60]!r}")
        if "<think>" in text.lower():
            print(f"{WARN} response contained a <think> block: this model emits reasoning")
            print("       inline. Schema-constrained decoding (step 3) must suppress it,")
            print("       since the <think>-stripping wrapper was removed.")
    except Exception as exc:  # noqa: BLE001
        print(f"{NO} cannot reach endpoint: {type(exc).__name__}: {exc}")
        print(f"    Is the local vLLM/Ollama server running at {base_url} ?")
        return 1

    # ------------------------------------------------------------------ 3
    _section("3. JSON-Schema structured output  (the NativeOutput requirement)")
    probe_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You output only JSON."},
                {"role": "user", "content": 'Return {"ok": true}'},
            ],
            temperature=0.0,
            stream=False,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "Probe", "schema": probe_schema, "strict": True},
            },
        )
        out = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(out)
        if isinstance(parsed, dict) and "ok" in parsed:
            native_ok = True
            print(f"{OK} server honoured response_format=json_schema  ->  NativeOutput works")
            print(f"{DOT} returned: {out[:80]}")
        else:
            print(f"{WARN} server accepted json_schema but returned an odd shape: {out[:100]}")
            failures += 1
    except Exception as exc:  # noqa: BLE001
        print(f"{NO} server rejected response_format=json_schema: {type(exc).__name__}: {str(exc)[:160]}")
        print("    => NativeOutput is NOT supported on this endpoint; the detectors will")
        print("       fail at runtime. Fix by enabling structured outputs on the server")
        print("       (vLLM guided decoding / recent Ollama), OR switch the detectors back")
        print("       to PromptedOutput(json_object).")
        failures += 1

    # ------------------------------------------------------------------ 4
    _section("4. Production detectors  (real PydanticAI + NativeOutput path)")
    sample = (
        "Hi, I'm Alice Chen at Acme Corp (alice@acme.com). My salary is $120,000, "
        "my performance review is on March 3rd, 2026, and my bonus rate is 7%."
    )
    try:
        from cloakbot.privacy.core.detection.detector import PiiDetector

        detector = PiiDetector()
        t0 = time.perf_counter()
        result = await detector.detect(sample)
        dt = (time.perf_counter() - t0) * 1000
        entities = [(e.text, e.entity_type) for e in result.entities]
        print(f"{OK} PiiDetector returned {len(entities)} entities in {dt:.0f} ms")
        for surface, etype in entities:
            print(f"{DOT} {etype:12} {surface!r}")
        if not entities:
            print(f"{WARN} no entities extracted — check model quality or that schema decoding")
            print("       isn't over-constraining the small model.")
        if "<think>" in (result.llm_raw_output or "").lower():
            print(f"{WARN} raw detector output contained <think> — the removed wrapper would")
            print("       have stripped this. Confirm json-schema decoding suppresses it.")
    except Exception as exc:  # noqa: BLE001
        print(f"{NO} detector run failed: {type(exc).__name__}: {str(exc)[:200]}")
        if not native_ok:
            print("    (Expected: step 3 already showed json_schema is unsupported.)")
        failures += 1

    # ------------------------------------------------------------------ 5
    _section("5. Intent classifier")
    try:
        from cloakbot.privacy.agents.classification.intent_analyzer import analyze_user_intent

        cases = [
            ("Summarize the attached report for me.", "chat"),
            ("If my salary is $120,000, what is a 7% raise worth?", "math"),
        ]
        for text, expected in cases:
            intent = await analyze_user_intent(text)
            got = intent.value
            mark = OK if got == expected else WARN
            print(f"{mark} intent={got:<5} (expected {expected:<4}) for: {text!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"{NO} intent classification failed: {type(exc).__name__}: {str(exc)[:200]}")
        failures += 1

    # ------------------------------------------------------------------ summary
    _section("Summary")
    if failures == 0 and native_ok:
        print(f"{OK} All checks passed — NativeOutput is honoured and detectors work here.")
        return 0
    if not native_ok:
        print(f"{NO} NativeOutput is not usable on this endpoint (see step 3) — must fix.")
    print(f"    {failures} failing check(s) above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
