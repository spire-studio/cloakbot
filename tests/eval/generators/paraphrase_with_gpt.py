"""Paraphrase multi-turn eval templates with GPT while preserving slot tokens.

Reads ``OPENAI_API_KEY`` and ``OPENAI_API_BASE`` from ``.env`` at the repo
root. GPT only sees the template's natural-language turns; it is forbidden
from inventing or dropping any ``{slot}`` token (it MAY move tokens across
turns, which is good — it widens the alias-consistency test surface).

Variants that violate the slot-preservation contract are rejected at parse
time, so the filler downstream always sees a coherent placeholder skeleton.

GPT call audit (model, token counts, rejected variants, raw response) is
appended to ``tests/eval/reports/gpt_audit.jsonl`` for transparency.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

_SLOT_RE = re.compile(r"\{(\w+)\}")

SYSTEM_PROMPT = """You rewrite multi-turn conversations into natural-language variants while preserving placeholder tokens.

HARD RULES (a single violation rejects the entire variant):
1. Each variant must have the same number of turns as the original, in the same order, with the same role per turn.
2. Every {slot_name} from the original MUST appear at least once somewhere in the variant. You MAY move a token to a different turn than the original. You MUST NOT invent new {tokens}, drop any original {token}, or change a token's spelling, casing, or braces.
3. Do not introduce literal personal data (names, phone numbers, addresses, dates, dollar amounts, IDs). Every piece of PII must live inside a {slot} token.
4. Be structurally aggressive across variants:
   - Vary register (clipped / casual / formal / verbose).
   - Reorder information flow — the caller may dump everything in turn 1, hold details back until the agent asks, or volunteer information the agent didn't request.
   - The agent may push back, summarize what it heard, propose alternatives, or ask a more specific clarifying question instead of the generic "confirm contact details".
   - Vary turn length — some turns 1 short sentence, others 3-4 sentences.
   - Vary which speaker introduces a given fact when that's plausible.
5. Keep the conversational outcome intact (the same business goal still gets accomplished).

OUTPUT FORMAT (strict JSON, no prose, no markdown fences):
{"variants": [{"turns": ["turn 1 text", "turn 2 text", ...]}, ...]}
"""


def _slots_in_text(text: str) -> set[str]:
    return {m.group(1) for m in _SLOT_RE.finditer(text)}


def _expected_slots(template: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for t in template["turns"]:
        out |= _slots_in_text(t["text"])
    return out


def _validate(
    variant: dict[str, Any],
    expected_roles: list[str],
    expected_slots: set[str],
) -> tuple[bool, str]:
    if not isinstance(variant, dict) or "turns" not in variant:
        return False, "missing 'turns' key"
    turns = variant["turns"]
    if not isinstance(turns, list):
        return False, "'turns' is not a list"
    if len(turns) != len(expected_roles):
        return False, f"turn count {len(turns)} != expected {len(expected_roles)}"
    seen: set[str] = set()
    for i, text in enumerate(turns):
        if not isinstance(text, str):
            return False, f"turn {i} is not a string"
        in_turn = _slots_in_text(text)
        novel = in_turn - expected_slots
        if novel:
            return False, f"turn {i} introduces unknown slots: {sorted(novel)}"
        seen |= in_turn
    missing = expected_slots - seen
    if missing:
        return False, f"variant drops slots: {sorted(missing)}"
    return True, ""


def paraphrase_via_gpt(
    template: dict[str, Any],
    n_variants: int,
    model: str,
    temperature: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Call GPT and validate. Returns (accepted_variants, audit, raw_response)."""
    expected_roles = [t["role"] for t in template["turns"]]
    expected_slots = _expected_slots(template)

    lines = [f"Produce {n_variants} variants.", "", "Original conversation:"]
    for i, t in enumerate(template["turns"], start=1):
        lines.append(f"TURN {i} ({t['role']}): {' '.join(t['text'].split())}")
    user_msg = "\n".join(lines)

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_API_BASE") or None,
    )
    # Some GPT proxies return upstream-saturation 429s under bursty load.
    # Exponential backoff (10s → 20s → 40s) covers the common transient
    # spike without burning the whole eval run on a single retry.
    delays = [10, 20, 40, 80]
    resp = None
    for attempt, delay in enumerate([0, *delays]):
        if delay:
            print(f"  retry in {delay}s …", file=sys.stderr)
            time.sleep(delay)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            break
        except RateLimitError as exc:
            if attempt == len(delays):
                raise
            print(f"  rate limit ({exc.code or 429}); will retry", file=sys.stderr)
    assert resp is not None
    content = resp.choices[0].message.content or "{}"

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"GPT returned malformed JSON: {e}", file=sys.stderr)
        parsed = {"variants": []}

    raw_variants = parsed.get("variants", []) if isinstance(parsed, dict) else []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for i, v in enumerate(raw_variants):
        ok, why = _validate(v, expected_roles, expected_slots)
        if ok:
            accepted.append({
                "id": f"{template['id']}_p{i:02d}",
                "turns": [
                    {"role": expected_roles[j], "text": v["turns"][j].strip()}
                    for j in range(len(expected_roles))
                ],
            })
        else:
            rejected.append({"index": i, "reason": why})

    audit = {
        "template_id": template["id"],
        "model": model,
        "temperature": temperature,
        "n_requested": n_variants,
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "rejected": rejected,
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
        "completion_tokens": getattr(resp.usage, "completion_tokens", None),
    }
    return accepted, audit, content


def _write_audit(audit: dict[str, Any], raw_response: str) -> None:
    audit_path = REPO_ROOT / "tests" / "eval" / "reports" / "gpt_audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    record = {**audit, "raw_response": raw_response}
    with audit_path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--variants", type=int, default=5)
    parser.add_argument(
        "--model",
        default=os.environ.get("EVAL_PARAPHRASE_MODEL", "gpt-5.4"),
    )
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument(
        "--out",
        type=Path,
        help="If set, write accepted variants to this YAML file.",
    )
    args = parser.parse_args()

    if "OPENAI_API_KEY" not in os.environ:
        print(
            "OPENAI_API_KEY not set. Put it in .env at the repo root or export it.",
            file=sys.stderr,
        )
        sys.exit(2)

    with args.template.open() as f:
        template = yaml.safe_load(f)

    print(
        f"→ paraphrasing {template['id']!r} into {args.variants} variants "
        f"via {args.model} (temperature={args.temperature})",
        file=sys.stderr,
    )

    accepted, audit, raw = paraphrase_via_gpt(
        template, args.variants, args.model, args.temperature
    )
    _write_audit(audit, raw)

    print(
        f"\n✓ {audit['n_accepted']}/{audit['n_requested']} variants accepted "
        f"({audit['n_rejected']} rejected). "
        f"Tokens: prompt={audit['prompt_tokens']} completion={audit['completion_tokens']}\n",
        file=sys.stderr,
    )
    for r in audit["rejected"]:
        print(f"  ✗ variant {r['index']}: {r['reason']}", file=sys.stderr)

    for v in accepted:
        print(f"\n--- {v['id']} ---")
        for t in v["turns"]:
            print(f"[{t['role']:9}] {t['text']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as f:
            yaml.safe_dump(
                {"template_id": template["id"], "variants": accepted},
                f,
                allow_unicode=True,
                sort_keys=False,
            )
        print(f"\nWrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
