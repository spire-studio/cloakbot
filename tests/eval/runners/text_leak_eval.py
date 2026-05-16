"""End-to-end leak eval for ``PrivacyRuntime.prepare_turn``.

Realises (paraphrased variant × Faker seed) combinations into multi-turn
sessions, drives each user turn through the privacy pipeline, and scores
whether any ground-truth value reached the upstream-bound prepared text.

Three things to know if you're reading this fresh:

1. Ground truth lives in the eval harness, not in the model. Slot values
   come from Faker with a fixed seed, so the same value can be searched for
   in the prepared text byte-for-byte. No model is in the grading loop.
2. Each (variant, seed) pair gets its own session_key so the vault does not
   leak across cases. Vault files are cleaned before and after the run.
3. ``alias_consistency_across_turns`` is the metric you care about for
   multi-turn privacy. It only makes sense for entities that recur, and is
   computed by checking that every recurrence of one original value gets
   replaced by the *same* placeholder in the prepared text.

Outputs:
  reports/<YYYY-MM-DD>/text_leak.jsonl   one record per session
  reports/<YYYY-MM-DD>/text_leak.md      human-readable summary
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

# Late import so .env is in place before CloakBot config reads it.
from loguru import logger  # noqa: E402

from cloakbot.config.paths import get_privacy_vault_dir  # noqa: E402
from cloakbot.privacy.core.state.vault import clear_cache, get_map  # noqa: E402
from cloakbot.privacy.runtime.pipeline import PrivacyRuntime  # noqa: E402
from tests.eval.generators.faker_filler import (  # noqa: E402
    Session,
    load_template,
    realize_paraphrased_session,
)

# ---------------------------------------------------------------------------
# Per-session evaluation
# ---------------------------------------------------------------------------


def _user_turn_indices(sess: Session) -> list[int]:
    return [i for i, t in enumerate(sess.turns) if t.role == "user"]


async def _run_one_session(
    runtime: PrivacyRuntime,
    sess: Session,
    *,
    session_key: str,
) -> dict[str, Any]:
    """Drive every user turn through prepare_turn; return raw observations."""
    clear_cache(session_key)
    user_indices = _user_turn_indices(sess)

    per_turn: list[dict[str, Any]] = []
    for i in user_indices:
        turn = sess.turns[i]
        t0 = time.perf_counter()
        prepared, _ctx = await runtime.prepare_turn(turn.text, session_key)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        prepared_text = (
            prepared
            if isinstance(prepared, str)
            else " ".join(b.get("text", "") for b in prepared if b.get("type") == "text")
        )
        per_turn.append(
            {
                "turn_index": i,
                "raw_text": turn.text,
                "prepared_text": prepared_text,
                "latency_ms": elapsed_ms,
            }
        )

    smap = get_map(session_key)
    return {
        "session_key": session_key,
        "template_id": sess.template_id,
        "seed": sess.seed,
        "user_turns": per_turn,
        "entities": [
            {"slot": e.slot, "type": e.type, "value": e.value} for e in sess.entities
        ],
        "vault": dict(smap.original_to_placeholder),
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"\w+")


def _ident_tokens(value: str) -> list[str]:
    """Identifying tokens that should be masked out of prepared text.

    The detector sometimes splits a multi-token entity (e.g. an address into
    house number + ZIP, leaving the street name exposed). A full-value
    substring match would hide that — token-level checks surface it.

    Filters:
      • digit-only tokens of length >= 3 (postal codes, IDs, street numbers).
      • alpha-only tokens of length >= 4 (names, cities, drugs, conditions).
    Shorter tokens (e.g. US state codes like "AS") are excluded because they
    are too ambiguous to score as leaks without false positives.
    """
    out: list[str] = []
    for t in _TOKEN_RE.findall(value):
        if t.isdigit() and len(t) >= 3:
            out.append(t)
        elif t.isalpha() and len(t) >= 4:
            out.append(t)
    return out


def _protecting_placeholder(value: str, vault: dict[str, str]) -> str | None:
    """Find the placeholder most likely to be the one protecting ``value``.

    The detector may extract a superset (``"Dr. Megan Mcclain"`` for
    ground-truth ``"Megan Mcclain"``) or a token-split (``"65423"`` and
    ``"06196"`` for a full address). We score every vault key by how many
    of the ground-truth's identifying tokens it shares; the placeholder for
    the highest-overlap key wins, ties broken by longer vault key (richer
    coverage).
    """
    gt_tokens = set(_ident_tokens(value))
    if not gt_tokens or not vault:
        return None
    best: tuple[int, int, str] | None = None  # (overlap, key_len, placeholder)
    for vault_key, placeholder in vault.items():
        vk_tokens = set(_ident_tokens(vault_key))
        overlap = len(gt_tokens & vk_tokens)
        if overlap == 0:
            continue
        score = (overlap, len(vault_key), placeholder)
        if best is None or score > best:
            best = score
    return best[2] if best else None


def _score_session(obs: dict[str, Any]) -> dict[str, Any]:
    """Token-level leak detection + token-overlap alias consistency."""
    entities = obs["entities"]
    user_turns = obs["user_turns"]
    vault = obs["vault"]

    # Per-pair counters: (entity occurrence in user turn) is one pair.
    total_pairs = 0
    leaked_pairs = 0  # ANY identifying token leaked
    total_tokens = 0
    leaked_tokens = 0
    per_type_total_pairs: dict[str, int] = defaultdict(int)
    per_type_leaked_pairs: dict[str, int] = defaultdict(int)
    per_type_total_tokens: dict[str, int] = defaultdict(int)
    per_type_leaked_tokens: dict[str, int] = defaultdict(int)
    leak_records: list[dict[str, Any]] = []

    for ent in entities:
        value = ent["value"]
        etype = ent["type"]
        idents = _ident_tokens(value)
        if not idents:
            continue
        # Appearance check uses full-value substring (not any-ident-token) to
        # avoid false positives where one entity's identifying token coincides
        # with another entity's name — e.g. surname "Johnson" appearing in
        # both a person name and a company name.
        for turn in user_turns:
            if value not in turn["raw_text"]:
                continue
            total_pairs += 1
            per_type_total_pairs[etype] += 1
            leaks_in_turn = [t for t in idents if t in turn["prepared_text"]]
            total_tokens += len(idents)
            per_type_total_tokens[etype] += len(idents)
            leaked_tokens += len(leaks_in_turn)
            per_type_leaked_tokens[etype] += len(leaks_in_turn)
            if leaks_in_turn:
                leaked_pairs += 1
                per_type_leaked_pairs[etype] += 1
                leak_records.append(
                    {
                        "turn_index": turn["turn_index"],
                        "type": etype,
                        "slot": ent["slot"],
                        "value": value,
                        "leaked_tokens": leaks_in_turn,
                    }
                )

    per_type_pair_recall: dict[str, float] = {
        etype: 1.0 - per_type_leaked_pairs.get(etype, 0) / total
        for etype, total in per_type_total_pairs.items()
    }
    per_type_token_recall: dict[str, float] = {
        etype: 1.0 - per_type_leaked_tokens.get(etype, 0) / total
        for etype, total in per_type_total_tokens.items()
    }

    # Alias consistency over recurring entities. We pick the placeholder that
    # most plausibly protects each entity (max token overlap with vault keys)
    # and check that placeholder appears in every turn the entity appeared in.
    # Same full-value-substring rule as the leak loop above — token-overlap
    # appearance counting collides across entities that share a surname.
    consistent_entities = 0
    multi_turn_entities = 0
    for ent in entities:
        value = ent["value"]
        appearances = [t for t in user_turns if value in t["raw_text"]]
        if len(appearances) < 2:
            continue
        placeholder = _protecting_placeholder(value, vault)
        if not placeholder:
            continue
        multi_turn_entities += 1
        if all(placeholder in t["prepared_text"] for t in appearances):
            consistent_entities += 1

    alias_consistency = (
        consistent_entities / multi_turn_entities if multi_turn_entities else None
    )

    latencies = [t["latency_ms"] for t in user_turns]

    return {
        "session_key": obs["session_key"],
        "template_id": obs["template_id"],
        "seed": obs["seed"],
        "n_user_turns": len(user_turns),
        "n_entities": len(entities),
        "total_entity_turn_pairs": total_pairs,
        "leaked_pairs": leaked_pairs,
        "pair_leak_rate": leaked_pairs / total_pairs if total_pairs else 0.0,
        "total_tokens": total_tokens,
        "leaked_tokens": leaked_tokens,
        "token_leak_rate": leaked_tokens / total_tokens if total_tokens else 0.0,
        "per_type_total_pairs": dict(per_type_total_pairs),
        "per_type_leaked_pairs": dict(per_type_leaked_pairs),
        "per_type_pair_recall": per_type_pair_recall,
        "per_type_total_tokens": dict(per_type_total_tokens),
        "per_type_leaked_tokens": dict(per_type_leaked_tokens),
        "per_type_token_recall": per_type_token_recall,
        "alias_consistency": alias_consistency,
        "multi_turn_entities": multi_turn_entities,
        "leak_records": leak_records,
        "turn_latencies_ms": latencies,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll session scores up into one report-friendly dict.

    Two recall granularities flow through:

    * **pair_leak_rate**: a pair is one (entity occurrence, user turn). The
      pair leaks if ANY identifying token from the entity reached prepared
      text. This is the headline number — even a partial leak counts.
    * **token_leak_rate**: fraction of identifying tokens that leaked
      across all pairs. Sharper when an entity has many tokens and only
      some leaked (e.g. address with house number masked but street name
      exposed).
    """
    total_pairs = sum(s["total_entity_turn_pairs"] for s in scores)
    leaked_pairs = sum(s["leaked_pairs"] for s in scores)
    total_tokens = sum(s["total_tokens"] for s in scores)
    leaked_tokens = sum(s["leaked_tokens"] for s in scores)

    per_type_total_pairs: dict[str, int] = defaultdict(int)
    per_type_leaked_pairs: dict[str, int] = defaultdict(int)
    per_type_total_tokens: dict[str, int] = defaultdict(int)
    per_type_leaked_tokens: dict[str, int] = defaultdict(int)
    for s in scores:
        for etype, n in s["per_type_total_pairs"].items():
            per_type_total_pairs[etype] += n
        for etype, n in s["per_type_leaked_pairs"].items():
            per_type_leaked_pairs[etype] += n
        for etype, n in s["per_type_total_tokens"].items():
            per_type_total_tokens[etype] += n
        for etype, n in s["per_type_leaked_tokens"].items():
            per_type_leaked_tokens[etype] += n

    per_type_pair_recall = {
        etype: 1.0 - per_type_leaked_pairs.get(etype, 0) / per_type_total_pairs[etype]
        for etype in per_type_total_pairs
    }
    per_type_token_recall = {
        etype: 1.0 - per_type_leaked_tokens.get(etype, 0) / per_type_total_tokens[etype]
        for etype in per_type_total_tokens
    }

    multi_turn_entities = sum(s["multi_turn_entities"] for s in scores)
    consistent_entities = sum(
        s["multi_turn_entities"] * s["alias_consistency"]
        for s in scores
        if s["alias_consistency"] is not None
    )
    alias_consistency = (
        consistent_entities / multi_turn_entities if multi_turn_entities else None
    )

    latencies = [latency for s in scores for latency in s["turn_latencies_ms"]]
    latencies.sort()

    def _pctile(values: list[float], q: float) -> float | None:
        if not values:
            return None
        k = min(len(values) - 1, int(round(q * (len(values) - 1))))
        return values[k]

    return {
        "n_sessions": len(scores),
        "total_entity_turn_pairs": total_pairs,
        "leaked_pairs": leaked_pairs,
        "pair_leak_rate": leaked_pairs / total_pairs if total_pairs else 0.0,
        "total_tokens": total_tokens,
        "leaked_tokens": leaked_tokens,
        "token_leak_rate": leaked_tokens / total_tokens if total_tokens else 0.0,
        "per_type_total_pairs": dict(per_type_total_pairs),
        "per_type_leaked_pairs": dict(per_type_leaked_pairs),
        "per_type_pair_recall": per_type_pair_recall,
        "per_type_total_tokens": dict(per_type_total_tokens),
        "per_type_leaked_tokens": dict(per_type_leaked_tokens),
        "per_type_token_recall": per_type_token_recall,
        "alias_consistency_across_turns": alias_consistency,
        "multi_turn_entities_total": multi_turn_entities,
        "p50_turn_latency_ms": median(latencies) if latencies else None,
        "p95_turn_latency_ms": _pctile(latencies, 0.95),
        "p99_turn_latency_ms": _pctile(latencies, 0.99),
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _render_markdown(
    agg: dict[str, Any],
    scores: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    lines = [
        f"# Text leak eval — {config['date']}",
        "",
        f"- **Template:** `{config['template_id']}`",
        f"- **Variants:** {config['n_variants']} (paraphrased; slots preserved)",
        f"- **Seeds per variant:** {config['n_seeds']}",
        f"- **Total sessions:** {agg['n_sessions']}",
        f"- **Detector:** {config['detector_model']} via vLLM @ {config['vllm_base_url']}",
        "",
        "Leaks are measured at two granularities. A **pair** is one (entity, "
        "user turn). A pair leaks if ANY identifying token from the entity "
        "reaches prepared text. **Token leak rate** is the fraction of "
        "identifying tokens that escaped — sharper when a multi-token entity "
        "(like a full address) is only partially masked.",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Entity-turn pairs | {agg['total_entity_turn_pairs']} |",
        f"| Leaked pairs | {agg['leaked_pairs']} |",
        f"| **Pair leak rate** | **{agg['pair_leak_rate']:.2%}** |",
        f"| Identifying tokens | {agg['total_tokens']} |",
        f"| Leaked tokens | {agg['leaked_tokens']} |",
        f"| **Token leak rate** | **{agg['token_leak_rate']:.2%}** |",
        f"| Alias consistency across turns | {_fmt_optpct(agg['alias_consistency_across_turns'])} |",
        f"| Multi-turn recurring entities | {agg['multi_turn_entities_total']} |",
        f"| p50 turn latency | {_fmt_optms(agg['p50_turn_latency_ms'])} |",
        f"| p95 turn latency | {_fmt_optms(agg['p95_turn_latency_ms'])} |",
        f"| p99 turn latency | {_fmt_optms(agg['p99_turn_latency_ms'])} |",
        "",
        "## Per-entity-type recall",
        "",
        "| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for etype in sorted(agg["per_type_total_pairs"]):
        pair_total = agg["per_type_total_pairs"][etype]
        pair_leak = agg["per_type_leaked_pairs"].get(etype, 0)
        tok_total = agg["per_type_total_tokens"].get(etype, 0)
        tok_leak = agg["per_type_leaked_tokens"].get(etype, 0)
        lines.append(
            f"| `{etype}` | {agg['per_type_pair_recall'][etype]:.2%} | "
            f"{agg['per_type_token_recall'].get(etype, 1.0):.2%} | "
            f"{pair_total} | {pair_leak} | {tok_total} | {tok_leak} |"
        )

    leak_records = [(s["session_key"], r) for s in scores for r in s["leak_records"]]
    if leak_records:
        lines.extend(
            [
                "",
                "## First leaks (truncated to 15)",
                "",
                "| Session | Turn | Type | Slot | Value | Leaked tokens |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for sess_key, r in leak_records[:15]:
            tokens_display = ", ".join(f"`{t}`" for t in r["leaked_tokens"])
            lines.append(
                f"| `{sess_key}` | {r['turn_index']} | "
                f"`{r['type']}` | `{r['slot']}` | `{r['value']}` | {tokens_display} |"
            )

    lines.extend(
        [
            "",
            "## Per-session leak summary",
            "",
            "| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for s in scores:
        lines.append(
            f"| `{s['session_key']}` | {s['total_entity_turn_pairs']} | "
            f"{s['leaked_pairs']} | {s['pair_leak_rate']:.2%} | "
            f"{s['token_leak_rate']:.2%} | "
            f"{_fmt_optpct(s['alias_consistency'])} |"
        )
    return "\n".join(lines) + "\n"


def _fmt_optpct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2%}"


def _fmt_optms(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0f} ms"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _cleanup_eval_vaults() -> None:
    """Remove any leftover eval vault files so runs are independent."""
    maps_dir = get_privacy_vault_dir() / "maps"
    if not maps_dir.exists():
        return
    for f in maps_dir.iterdir():
        if f.is_file() and f.name.startswith("eval"):
            try:
                f.unlink()
            except OSError:
                pass


async def _drive(
    template_path: Path,
    paraphrased_path: Path,
    seeds: list[int],
    *,
    channel: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run all (variant, seed) sessions and return (observations, scores)."""
    template = load_template(template_path)
    with paraphrased_path.open() as f:
        paraphrased = yaml.safe_load(f)
    variants = paraphrased["variants"]

    runtime = PrivacyRuntime(channel=channel)
    observations: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []

    for variant in variants:
        for seed in seeds:
            sess = realize_paraphrased_session(template, variant, seed)
            session_key = f"eval:{template['id']}:{variant['id']}:{seed}"
            print(
                f"  → {session_key} ({len(_user_turn_indices(sess))} user turns)",
                file=sys.stderr,
            )
            obs = await _run_one_session(runtime, sess, session_key=session_key)
            score = _score_session(obs)
            observations.append(obs)
            scores.append(score)
    return observations, scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=REPO_ROOT / "tests/eval/templates/medical_followup_v1.yaml",
    )
    parser.add_argument(
        "--paraphrased",
        type=Path,
        default=REPO_ROOT
        / "tests/eval/corpus/generated/medical_followup_v1.paraphrased.yaml",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[42, 137, 256, 1024],
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Override report directory (default: reports/<today>).",
    )
    parser.add_argument(
        "--channel",
        default="eval",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress loguru INFO output from CloakBot.",
    )
    args = parser.parse_args()

    if args.quiet:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    base = os.environ.get("VLLM_BASE_URL", "unset")
    model = os.environ.get("VLLM_MODEL", "google/gemma-4-E2B-it")
    print(f"vLLM target: {base} ({model})", file=sys.stderr)
    if base == "unset":
        print(
            "⚠ VLLM_BASE_URL not set; detector will run in fail-open mode and "
            "all sessions will report 100% leaks.",
            file=sys.stderr,
        )

    print("Cleaning leftover eval vaults …", file=sys.stderr)
    _cleanup_eval_vaults()

    observations, scores = asyncio.run(
        _drive(args.template, args.paraphrased, args.seeds, channel=args.channel)
    )
    agg = _aggregate(scores)

    today = dt.date.today().isoformat()
    out_dir = args.out_dir or REPO_ROOT / "tests/eval/reports" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    template_id = load_template(args.template)["id"]
    jsonl_path = out_dir / f"text_leak.{template_id}.jsonl"
    md_path = out_dir / f"text_leak.{template_id}.md"

    with jsonl_path.open("w") as f:
        for s in scores:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
        f.write(json.dumps({"_aggregate": agg}, ensure_ascii=False) + "\n")

    config = {
        "date": today,
        "template_id": load_template(args.template)["id"],
        "n_variants": len(yaml.safe_load(args.paraphrased.open())["variants"]),
        "n_seeds": len(args.seeds),
        "detector_model": model,
        "vllm_base_url": base,
    }
    md = _render_markdown(agg, scores, config)
    md_path.write_text(md)

    print(f"\nWrote {jsonl_path}", file=sys.stderr)
    print(f"Wrote {md_path}", file=sys.stderr)
    print(
        f"\nPair leak: {agg['pair_leak_rate']:.2%}  "
        f"token leak: {agg['token_leak_rate']:.2%}  "
        f"alias consistency: {_fmt_optpct(agg['alias_consistency_across_turns'])}  "
        f"p95 latency: {_fmt_optms(agg['p95_turn_latency_ms'])}",
        file=sys.stderr,
    )

    _cleanup_eval_vaults()


if __name__ == "__main__":
    main()
