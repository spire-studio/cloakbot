"""End-to-end leak eval for long-document handling through the tool boundary.

A1 (``text_leak_eval``) drives short user turns through
``PrivacyRuntime.prepare_turn``, which never exercises the chunker —
inputs under ~6000 characters take the single-shot detector path. This
runner targets the **tool-output path**, which is where long documents
actually live in CloakBot's contract: a tool returns a long payload, the
interceptor routes it through ``sanitize_tool_output_chunked``, and the
chunker splits the payload into ~6000-char windows before per-chunk PII
detection.

What this runner adds on top of the A1 metric set:

1. **Chunker activation** — how many chunks each long document split
   into, and whether any chunk's detection failed (which forces the
   pipeline into a fail-closed omit).
2. **Seam-leak attribution** — for every identifying token that leaked,
   how far the token sits from the nearest chunk seam in the raw
   document. Tokens within the overlap window of a seam tell us the
   seam-overlap heuristic is not catching them; tokens deep inside a
   chunk tell us a chunk-local detection miss.
3. **Cross-path alias consistency** — after the long document is
   tokenized via the tool path, a short follow-up user turn re-mentions
   key entities by name. The follow-up goes through
   ``prepare_turn`` (the user-input path) on the same session_key. We
   check that placeholders coined on the tool side are re-used on the
   input side, i.e. the vault carries across the path boundary.

Outputs:
  reports/<YYYY-MM-DD>/long_doc_leak.<template_id>.jsonl
  reports/<YYYY-MM-DD>/long_doc_leak.<template_id>.md
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

# Late imports so .env is in place before CloakBot config reads it.
from loguru import logger  # noqa: E402

from cloakbot.privacy.core.detection.chunking import (  # noqa: E402
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
)
from cloakbot.privacy.core.detection.chunking.text import PlainTextChunker  # noqa: E402
from cloakbot.privacy.core.sanitization.sanitize import sanitize_tool_output_chunked  # noqa: E402
from cloakbot.privacy.core.state.vault import clear_cache, get_map  # noqa: E402
from cloakbot.privacy.runtime.pipeline import PrivacyRuntime  # noqa: E402
from tests.eval.generators.faker_filler import (  # noqa: E402
    Session,
    load_template,
    realize_paraphrased_session,
)
from tests.eval.runners.text_leak_eval import (  # noqa: E402
    _aggregate,
    _cleanup_eval_vaults,
    _fmt_optms,
    _fmt_optpct,
    _protecting_placeholder,
    _score_session,
)

# ---------------------------------------------------------------------------
# Turn classification
# ---------------------------------------------------------------------------


def _classify_user_turns(sess: Session, *, long_threshold: int) -> tuple[int | None, list[int]]:
    """Return (long_turn_index, followup_turn_indices).

    The "long" turn is the first user turn whose realized text exceeds
    ``long_threshold`` characters — that's what we drive through the
    tool-output path. Every later user turn becomes a follow-up driven
    through ``prepare_turn`` on the same session_key.
    """
    long_idx: int | None = None
    followups: list[int] = []
    for i, t in enumerate(sess.turns):
        if t.role != "user":
            continue
        if long_idx is None and len(t.text) >= long_threshold:
            long_idx = i
        elif long_idx is not None:
            followups.append(i)
    return long_idx, followups


# ---------------------------------------------------------------------------
# Per-session evaluation
# ---------------------------------------------------------------------------


async def _run_one_session(
    runtime: PrivacyRuntime,
    sess: Session,
    *,
    session_key: str,
    long_threshold: int,
    tool_name: str,
) -> dict[str, Any]:
    """Drive the long turn through the tool path; follow-ups through prepare_turn."""
    clear_cache(session_key)
    long_idx, followup_indices = _classify_user_turns(sess, long_threshold=long_threshold)

    if long_idx is None:
        # No turn long enough — skip the tool path entirely and fall back
        # to the same prepare_turn flow as A1. The session is still scored
        # but contributes only to the "chunker_activated=False" bucket.
        logger.warning(
            "no user turn ≥{} chars in session {}; running all user turns "
            "through prepare_turn",
            long_threshold,
            session_key,
        )

    per_turn: list[dict[str, Any]] = []
    long_turn_meta: dict[str, Any] | None = None

    for i, turn in enumerate(sess.turns):
        if turn.role != "user":
            continue

        if i == long_idx:
            t0 = time.perf_counter()
            sanitized, modified, _entities, chunks_failed = await sanitize_tool_output_chunked(
                turn.text,
                session_key,
                tool_name=tool_name,
                turn_id=f"{session_key}:t{i}",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Independent chunker simulation to attribute seams.
            chunker = PlainTextChunker()
            chunks = chunker.chunk(turn.text)

            long_turn_meta = {
                "turn_index": i,
                "raw_chars": len(turn.text),
                "chunks_total": len(chunks),
                "chunks_failed": chunks_failed,
                "modified": modified,
                "chunk_spans": [c.char_span for c in chunks],
                "path": "tool_output_chunked",
            }
            per_turn.append(
                {
                    "turn_index": i,
                    "raw_text": turn.text,
                    "prepared_text": sanitized,
                    "latency_ms": elapsed_ms,
                    "path": "tool_output_chunked",
                }
            )
        else:
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
                    "path": "prepare_turn",
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
        "long_turn": long_turn_meta,
        "followup_indices": followup_indices,
    }


# ---------------------------------------------------------------------------
# Long-doc-specific metrics
# ---------------------------------------------------------------------------


def _seam_attribution(
    leak_records: list[dict[str, Any]],
    user_turns: list[dict[str, Any]],
    long_turn_meta: dict[str, Any] | None,
    *,
    overlap_chars: int,
) -> list[dict[str, Any]]:
    """For each long-turn leak, locate it in raw_text and measure seam proximity.

    A leak that sits within ``overlap_chars`` of a chunk seam is the
    most concerning class — the seam-overlap heuristic is supposed to
    catch exactly those, and a leak in that band means the overlap was
    insufficient. A leak deep inside a single chunk implies a per-chunk
    detection miss instead, which is a different failure mode.
    """
    if long_turn_meta is None:
        return []
    long_idx = long_turn_meta["turn_index"]
    long_turn = next((t for t in user_turns if t["turn_index"] == long_idx), None)
    if long_turn is None:
        return []

    raw = long_turn["raw_text"]
    spans = [s for s in long_turn_meta["chunk_spans"] if s is not None]
    # The seam offsets are the END of every chunk except the last
    # (equivalently, the START of every chunk except the first). Use the
    # end-of-chunk-N offset as the canonical seam location.
    seams = [end for _start, end in spans[:-1]]

    out: list[dict[str, Any]] = []
    for record in leak_records:
        if record["turn_index"] != long_idx:
            continue
        for token in record["leaked_tokens"]:
            # First occurrence is sufficient for attribution. A leaked
            # token typically appears once; if it recurs, the first
            # position tells us where the detector first failed.
            offset = raw.find(token)
            if offset < 0:
                continue
            if not seams:
                distance = None
                nearest = None
            else:
                nearest = min(seams, key=lambda s: abs(s - offset))
                distance = abs(nearest - offset)
            out.append(
                {
                    "turn_index": long_idx,
                    "token": token,
                    "char_offset": offset,
                    "nearest_seam": nearest,
                    "distance_from_seam_chars": distance,
                    "within_overlap_band": (
                        distance is not None and distance <= overlap_chars
                    ),
                    "type": record["type"],
                    "slot": record["slot"],
                }
            )
    return out


def _cross_path_alias_check(
    entities: list[dict[str, Any]],
    user_turns: list[dict[str, Any]],
    vault: dict[str, str],
    long_turn_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Did placeholders coined in the tool path survive into prepare_turn output?

    For every entity that appears in BOTH the long (tool-path) turn and
    in at least one follow-up (prepare_turn) turn, find the placeholder
    most likely to protect that value (max token overlap with vault
    keys, same heuristic as text_leak_eval's alias consistency) and
    check that the placeholder appears in BOTH paths' prepared text.
    The numerator/denominator are entities, not turn pairs.
    """
    if long_turn_meta is None:
        return {"checked": 0, "carried": 0, "rate": None}
    long_idx = long_turn_meta["turn_index"]
    long_turn = next((t for t in user_turns if t["turn_index"] == long_idx), None)
    followups = [t for t in user_turns if t["turn_index"] != long_idx]
    if long_turn is None or not followups:
        return {"checked": 0, "carried": 0, "rate": None}

    checked = 0
    carried = 0
    misses: list[dict[str, Any]] = []
    for ent in entities:
        value = ent["value"]
        if not value or value not in long_turn["raw_text"]:
            continue
        appears_in_followup = any(value in f["raw_text"] for f in followups)
        if not appears_in_followup:
            continue
        placeholder = _protecting_placeholder(value, vault)
        if not placeholder:
            continue
        checked += 1
        in_long = placeholder in long_turn["prepared_text"]
        in_followup = any(placeholder in f["prepared_text"] for f in followups)
        if in_long and in_followup:
            carried += 1
        else:
            misses.append(
                {
                    "value": value,
                    "slot": ent["slot"],
                    "placeholder": placeholder,
                    "in_long_prepared": in_long,
                    "in_followup_prepared": in_followup,
                }
            )

    return {
        "checked": checked,
        "carried": carried,
        "rate": carried / checked if checked else None,
        "misses": misses,
    }


# ---------------------------------------------------------------------------
# Scoring (extends text_leak_eval's _score_session)
# ---------------------------------------------------------------------------


def _score_session_long(
    obs: dict[str, Any], *, overlap_chars: int
) -> dict[str, Any]:
    base = _score_session(obs)
    long_meta = obs.get("long_turn")
    seams = _seam_attribution(
        base["leak_records"],
        obs["user_turns"],
        long_meta,
        overlap_chars=overlap_chars,
    )
    cross_path = _cross_path_alias_check(
        obs["entities"], obs["user_turns"], obs["vault"], long_meta
    )
    return {
        **base,
        "long_turn_chars": long_meta["raw_chars"] if long_meta else None,
        "chunks_total": long_meta["chunks_total"] if long_meta else None,
        "chunks_failed": long_meta["chunks_failed"] if long_meta else None,
        "chunker_activated": bool(long_meta and long_meta["chunks_total"] > 1),
        "seam_leaks": seams,
        "cross_path_alias": cross_path,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate_long(scores: list[dict[str, Any]]) -> dict[str, Any]:
    base = _aggregate(scores)

    activated = [s for s in scores if s["chunker_activated"]]
    failed = [s for s in scores if s.get("chunks_failed")]
    seam_leak_records = [seam for s in scores for seam in s["seam_leaks"]]
    in_band = [s for s in seam_leak_records if s["within_overlap_band"]]

    cross_checked = sum(s["cross_path_alias"]["checked"] for s in scores)
    cross_carried = sum(s["cross_path_alias"]["carried"] for s in scores)
    cross_rate = cross_carried / cross_checked if cross_checked else None

    chunk_counts = [s["chunks_total"] for s in scores if s["chunks_total"] is not None]

    return {
        **base,
        "n_chunker_activated": len(activated),
        "n_chunks_failed_sessions": len(failed),
        "p50_chunks_per_long_doc": median(chunk_counts) if chunk_counts else None,
        "max_chunks_per_long_doc": max(chunk_counts) if chunk_counts else None,
        "seam_leaks_total": len(seam_leak_records),
        "seam_leaks_within_overlap": len(in_band),
        "cross_path_alias_checked": cross_checked,
        "cross_path_alias_carried": cross_carried,
        "cross_path_alias_rate": cross_rate,
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
        f"# Long-document leak eval — {config['date']}",
        "",
        f"- **Template:** `{config['template_id']}`",
        f"- **Variants:** {config['n_variants']}",
        f"- **Seeds per variant:** {config['n_seeds']}",
        f"- **Total sessions:** {agg['n_sessions']}",
        f"- **Detector:** {config['detector_model']} via vLLM @ {config['vllm_base_url']}",
        f"- **Chunker:** plaintext, max_chars={config['chunker_max_chars']}, overlap={config['chunker_overlap']}",
        "",
        "Long-document content is driven through ``sanitize_tool_output_chunked`` "
        "(the chunker-backed tool-output path); short follow-up turns go through "
        "``prepare_turn`` on the same session, so vault carryover across the tool→input "
        "path boundary is testable.",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Sessions | {agg['n_sessions']} |",
        f"| Sessions where chunker activated (≥2 chunks) | {agg['n_chunker_activated']} |",
        f"| Sessions with at least one chunk failure | {agg['n_chunks_failed_sessions']} |",
        f"| p50 chunks per long doc | {agg['p50_chunks_per_long_doc']} |",
        f"| Max chunks per long doc | {agg['max_chunks_per_long_doc']} |",
        f"| Entity-turn pairs | {agg['total_entity_turn_pairs']} |",
        f"| Leaked pairs | {agg['leaked_pairs']} |",
        f"| **Pair leak rate** | **{agg['pair_leak_rate']:.2%}** |",
        f"| Identifying tokens | {agg['total_tokens']} |",
        f"| Leaked tokens | {agg['leaked_tokens']} |",
        f"| **Token leak rate** | **{agg['token_leak_rate']:.2%}** |",
        f"| Seam leaks (total) | {agg['seam_leaks_total']} |",
        f"| Seam leaks within overlap band ({config['chunker_overlap']}c) | {agg['seam_leaks_within_overlap']} |",
        f"| Cross-path alias consistency (tool→input) | {_fmt_optpct(agg['cross_path_alias_rate'])} ({agg['cross_path_alias_carried']}/{agg['cross_path_alias_checked']}) |",
        f"| Alias consistency across turns | {_fmt_optpct(agg['alias_consistency_across_turns'])} |",
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

    seam_records = [(s["session_key"], r) for s in scores for r in s["seam_leaks"]]
    if seam_records:
        lines.extend(
            [
                "",
                "## Seam attribution (long-turn leaks only, truncated to 20)",
                "",
                "| Session | Token | Offset | Nearest seam | Distance | In overlap band? | Type | Slot |",
                "|---|---|---:|---:|---:|:---:|---|---|",
            ]
        )
        for sess_key, r in seam_records[:20]:
            band = "yes" if r["within_overlap_band"] else "no"
            seam = r["nearest_seam"] if r["nearest_seam"] is not None else "—"
            dist = r["distance_from_seam_chars"] if r["distance_from_seam_chars"] is not None else "—"
            lines.append(
                f"| `{sess_key}` | `{r['token']}` | {r['char_offset']} | {seam} | "
                f"{dist} | {band} | `{r['type']}` | `{r['slot']}` |"
            )

    lines.extend(
        [
            "",
            "## Per-session summary",
            "",
            "| Session | Chars | Chunks | Failed? | Pair leaks | Token leak rate | Cross-path alias |",
            "|---|---:|---:|:---:|---:|---:|---|",
        ]
    )
    for s in scores:
        chunks_failed = "yes" if s["chunks_failed"] else "no"
        cross = s["cross_path_alias"]
        cross_str = (
            f"{cross['carried']}/{cross['checked']}"
            if cross["checked"]
            else "n/a"
        )
        lines.append(
            f"| `{s['session_key']}` | {s['long_turn_chars']} | {s['chunks_total']} | "
            f"{chunks_failed} | {s['leaked_pairs']} | "
            f"{s['token_leak_rate']:.2%} | {cross_str} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def _drive(
    template_path: Path,
    paraphrased_path: Path,
    seeds: list[int],
    *,
    channel: str,
    long_threshold: int,
    tool_name: str,
    overlap_chars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
            long_idx, _fu = _classify_user_turns(sess, long_threshold=long_threshold)
            long_chars = len(sess.turns[long_idx].text) if long_idx is not None else 0
            print(
                f"  → {session_key} (long_turn={long_idx} chars={long_chars})",
                file=sys.stderr,
            )
            obs = await _run_one_session(
                runtime,
                sess,
                session_key=session_key,
                long_threshold=long_threshold,
                tool_name=tool_name,
            )
            score = _score_session_long(obs, overlap_chars=overlap_chars)
            observations.append(obs)
            scores.append(score)
    return observations, scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--paraphrased", type=Path, required=True)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[42, 137, 256, 1024],
    )
    parser.add_argument(
        "--long-threshold",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Minimum realized user-turn char count to route through the "
        "tool-output (chunked) path.",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=DEFAULT_OVERLAP_CHARS,
        help="Chunker overlap window. Seam leaks within this band of a chunk "
        "boundary are reported as overlap-window failures.",
    )
    parser.add_argument("--tool-name", default="read_file")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--channel", default="eval")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.quiet:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    base = os.environ.get("GEMMA_BASE_URL", "unset")
    model = os.environ.get("GEMMA_MODEL", "google/gemma-4-E2B-it")
    print(f"Gemma detector target: {base} ({model})", file=sys.stderr)
    if base == "unset":
        print(
            "⚠ GEMMA_BASE_URL not set; detector will run in fail-open mode and "
            "all sessions will report 100% leaks.",
            file=sys.stderr,
        )

    print("Cleaning leftover eval vaults …", file=sys.stderr)
    _cleanup_eval_vaults()

    observations, scores = asyncio.run(
        _drive(
            args.template,
            args.paraphrased,
            args.seeds,
            channel=args.channel,
            long_threshold=args.long_threshold,
            tool_name=args.tool_name,
            overlap_chars=args.overlap_chars,
        )
    )
    agg = _aggregate_long(scores)

    today = dt.date.today().isoformat()
    out_dir = args.out_dir or REPO_ROOT / "tests/eval/reports" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    template_id = load_template(args.template)["id"]
    jsonl_path = out_dir / f"long_doc_leak.{template_id}.jsonl"
    md_path = out_dir / f"long_doc_leak.{template_id}.md"

    with jsonl_path.open("w") as f:
        for s in scores:
            f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")
        f.write(json.dumps({"_aggregate": agg}, ensure_ascii=False, default=str) + "\n")

    config = {
        "date": today,
        "template_id": template_id,
        "n_variants": len(yaml.safe_load(args.paraphrased.open())["variants"]),
        "n_seeds": len(args.seeds),
        "detector_model": model,
        "vllm_base_url": base,
        "chunker_max_chars": DEFAULT_MAX_CHARS,
        "chunker_overlap": args.overlap_chars,
    }
    md = _render_markdown(agg, scores, config)
    md_path.write_text(md)

    print(f"\nWrote {jsonl_path}", file=sys.stderr)
    print(f"Wrote {md_path}", file=sys.stderr)
    print(
        f"\nPair leak: {agg['pair_leak_rate']:.2%}  "
        f"token leak: {agg['token_leak_rate']:.2%}  "
        f"chunker-activated: {agg['n_chunker_activated']}/{agg['n_sessions']}  "
        f"seam leaks: {agg['seam_leaks_total']} ({agg['seam_leaks_within_overlap']} in band)  "
        f"cross-path alias: {_fmt_optpct(agg['cross_path_alias_rate'])}",
        file=sys.stderr,
    )

    _cleanup_eval_vaults()


if __name__ == "__main__":
    main()
