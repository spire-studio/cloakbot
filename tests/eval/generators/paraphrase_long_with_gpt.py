"""Paraphrase long-document eval templates with GPT while preserving slot tokens.

Sister script to :mod:`paraphrase_with_gpt`. The slot-preservation contract
is identical — every ``{slot}`` from the original must survive in the
variant, no new slots may be invented, no literal PII may be introduced —
but the system prompt asks GPT to **expand** the long user turn into a
multi-paragraph, professionally-registered document so that the post-Faker
realisation reliably exceeds the plaintext chunker's 6000-char window.

The expansion is the whole point: A1 templates are short enough that the
chunker is never exercised. A3 templates need to land in chunker territory
to test seam-boundary entity recovery. A variant whose long-turn user text
is too short still passes (slot-preservation is the hard contract; length
is a soft signal) but is flagged in the audit log so we can tell when GPT
under-expands and re-run if needed.

GPT call audit (model, token counts, rejected variants, per-turn lengths)
is appended to ``tests/eval/reports/gpt_audit.jsonl`` for transparency.
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

SYSTEM_PROMPT_LONG = """You rewrite long-document conversations into natural-language variants while preserving placeholder tokens.

The conversations you receive contain at least one long user turn — typically a letter, memo, ticket body, or report. Paraphrase that turn into a realistic, professionally-registered long-form document that a reader would mistake for an actual letter / email / ticket.

HARD RULES (a single violation rejects the entire variant):
1. STRUCTURE — Each variant must have exactly the same number of turns as the original, in the same order, with the same role per turn. The user message will tell you the explicit role sequence (e.g. user / assistant / user / assistant / user) — match it. Do not merge, drop, or reorder any turn, even a short acknowledgement turn that feels redundant. Output the same number of items in "turns" as roles in the sequence.
2. SLOT TOKENS — Every {slot_name} that appears anywhere in the original MUST appear at least once somewhere in your variant. You MAY move a token to a different turn than the original. You MUST NOT invent new {tokens}, drop any original {token}, or change a token's spelling, casing, or braces.
3. NO LITERAL PII — Do not introduce literal personal data (names, phone numbers, addresses, dates, dollar amounts, IDs, error codes, hostnames). Every piece of PII must live inside a {slot} token.
4. LENGTH — For each turn flagged as [LONG — EXPAND] in the user message: paraphrase faithfully and let it grow naturally to roughly 1.3x–1.8x the original character length, by elaborating on the section structure that is already there (procedural posture, business context, technical detail). Do not pad with empty filler. Do not chop the body down to a summary either.
5. REGISTER — Vary across variants: clipped formal / verbose corporate / dry procedural / detail-heavy operational. Keep the conversational outcome intact.

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
    """Hard slot-preservation contract. Length is checked separately by the
    caller and only feeds the audit log — it is not grounds for rejection.
    """
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


def _long_turn_indices(template: dict[str, Any], threshold: int) -> list[int]:
    """Indices of user turns whose original raw text exceeds ``threshold``.

    These are the turns we expect GPT to expand; any variant where one of
    these turns lands short is flagged (but not rejected) in the audit.
    """
    return [
        i
        for i, t in enumerate(template["turns"])
        if t["role"] == "user" and len(" ".join(t["text"].split())) >= threshold
    ]


def paraphrase_via_gpt(
    template: dict[str, Any],
    n_variants: int,
    model: str,
    temperature: float,
    *,
    long_turn_threshold: int,
    min_long_turn_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Call GPT and validate. Returns (accepted_variants, audit, raw_response)."""
    expected_roles = [t["role"] for t in template["turns"]]
    expected_slots = _expected_slots(template)
    long_indices = _long_turn_indices(template, long_turn_threshold)

    # Compute the per-long-turn minimum: the larger of the global floor
    # and 1.8x the original turn length. Giving GPT a per-turn target
    # anchored to the original is more reliable than a single global
    # floor because the model can compare directly against the text it
    # is rewriting.
    long_turn_minimums: dict[int, int] = {}
    for idx in long_indices:
        original_len = len(" ".join(template["turns"][idx]["text"].split()))
        long_turn_minimums[idx] = max(min_long_turn_chars, int(original_len * 1.8))

    role_sequence = " / ".join(expected_roles)

    lines = [
        f"Produce {n_variants} variants.",
        f"REQUIRED ROLE SEQUENCE (exactly {len(expected_roles)} turns): {role_sequence}",
        "Do not merge, drop, or reorder turns.",
        "",
    ]
    if long_indices:
        target_lines = [
            f"  - TURN {idx + 1} (1-indexed): original is "
            f"{len(' '.join(template['turns'][idx]['text'].split()))} chars; "
            f"your variant of this turn MUST be at least {long_turn_minimums[idx]} chars."
            for idx in long_indices
        ]
        lines.append("LONG-TURN EXPANSION TARGETS:")
        lines.extend(target_lines)
        lines.append("")
    lines.append("Original conversation:")
    for i, t in enumerate(template["turns"], start=1):
        is_long = (i - 1) in long_indices
        tag = " [LONG — EXPAND]" if is_long else ""
        lines.append(f"TURN {i} ({t['role']}){tag}: {' '.join(t['text'].split())}")
    user_msg = "\n".join(lines)

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_API_BASE") or None,
    )
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
                    {"role": "system", "content": SYSTEM_PROMPT_LONG},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                # Long-doc variants need 1500–2500 completion tokens each;
                # for ``--variants 5`` that is 8–12k tokens. Many proxies
                # default to ~4k and silently truncate, producing missing
                # ``turns`` keys or chopped-off final variants. 16k gives
                # comfortable headroom even on the verbose ticket genre.
                max_tokens=16000,
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
    underlength: list[dict[str, Any]] = []
    for i, v in enumerate(raw_variants):
        ok, why = _validate(v, expected_roles, expected_slots)
        if not ok:
            rejected.append({"index": i, "reason": why})
            continue
        turn_lengths = [len(t.strip()) for t in v["turns"]]
        short_long_turns = [
            {"turn_index": j, "chars": turn_lengths[j]}
            for j in long_indices
            if turn_lengths[j] < min_long_turn_chars
        ]
        if short_long_turns:
            underlength.append(
                {"index": i, "short_turns": short_long_turns}
            )
        accepted.append({
            "id": f"{template['id']}_p{i:02d}",
            "turns": [
                {"role": expected_roles[j], "text": v["turns"][j].strip()}
                for j in range(len(expected_roles))
            ],
            "turn_lengths": turn_lengths,
        })

    audit = {
        "template_id": template["id"],
        "model": model,
        "temperature": temperature,
        "n_requested": n_variants,
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "n_underlength": len(underlength),
        "long_turn_indices": long_indices,
        "min_long_turn_chars": min_long_turn_chars,
        "rejected": rejected,
        "underlength": underlength,
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
        "completion_tokens": getattr(resp.usage, "completion_tokens", None),
    }
    return accepted, audit, content


def _write_audit(audit: dict[str, Any], raw_response: str) -> None:
    audit_path = REPO_ROOT / "tests" / "eval" / "reports" / "gpt_audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    record = {**audit, "raw_response": raw_response, "kind": "paraphrase_long"}
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
        "--long-turn-threshold",
        type=int,
        default=1500,
        help="Original raw user-turn length above which a turn is considered "
        "a long-document turn that must be expanded.",
    )
    parser.add_argument(
        "--min-long-turn-chars",
        type=int,
        default=4500,
        help="Soft minimum char count for each long user turn in the variant. "
        "Variants under this are flagged in the audit but not rejected.",
    )
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
        f"→ paraphrasing {template['id']!r} (long-document) into "
        f"{args.variants} variants via {args.model} "
        f"(temperature={args.temperature}, "
        f"min_long_turn_chars={args.min_long_turn_chars})",
        file=sys.stderr,
    )

    accepted, audit, raw = paraphrase_via_gpt(
        template,
        args.variants,
        args.model,
        args.temperature,
        long_turn_threshold=args.long_turn_threshold,
        min_long_turn_chars=args.min_long_turn_chars,
    )
    _write_audit(audit, raw)

    print(
        f"\n✓ {audit['n_accepted']}/{audit['n_requested']} variants accepted "
        f"({audit['n_rejected']} rejected, {audit['n_underlength']} flagged "
        f"under-length). Tokens: prompt={audit['prompt_tokens']} "
        f"completion={audit['completion_tokens']}\n",
        file=sys.stderr,
    )
    for r in audit["rejected"]:
        print(f"  ✗ variant {r['index']}: {r['reason']}", file=sys.stderr)
    for u in audit["underlength"]:
        details = ", ".join(
            f"turn {s['turn_index']}={s['chars']}c" for s in u["short_turns"]
        )
        print(f"  ! variant {u['index']} short: {details}", file=sys.stderr)

    # Strip the per-variant turn_lengths debug field before persisting; the
    # downstream filler and runner do not consume it and including it in the
    # YAML adds noise without value.
    for v in accepted:
        v.pop("turn_lengths", None)

    for v in accepted:
        print(f"\n--- {v['id']} ---")
        for t in v["turns"]:
            print(f"[{t['role']:9}] ({len(t['text'])}c) {t['text'][:160]}…")

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
