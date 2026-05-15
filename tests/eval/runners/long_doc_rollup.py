"""Roll up per-template ``long_doc_leak.*.jsonl`` reports into one summary.

Sister script to :mod:`rollup` (which handles A1 ``text_leak.*.jsonl``).
Reads the final ``_aggregate`` record from each long-doc report and emits
a single markdown summary covering the A3-specific metrics — chunker
activation, seam attribution, cross-path alias carryover — alongside the
A1 leak/recall metrics it shares with the short-dialogue eval.

Usage:
    python -m tests.eval.runners.long_doc_rollup [--date 2026-05-15]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_aggregate(jsonl_path: Path) -> dict[str, Any] | None:
    last_agg: dict[str, Any] | None = None
    with jsonl_path.open() as f:
        for line in f:
            record = json.loads(line)
            if "_aggregate" in record:
                last_agg = record["_aggregate"]
    return last_agg


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2%}"


def _fmt_ms(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0f}"


def _domain_of(template_id: str) -> str:
    # Long-doc templates use ``long_<domain>_v1`` naming.
    stem = template_id.removeprefix("long_")
    for prefix in ("legal_correspondence", "email", "tech_ticket"):
        if stem.startswith(prefix):
            return prefix
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--reports-dir", type=Path, default=None)
    args = parser.parse_args()

    reports_dir = args.reports_dir or REPO_ROOT / "tests/eval/reports" / args.date
    if not reports_dir.exists():
        raise SystemExit(f"no reports directory at {reports_dir}")

    rows: list[tuple[str, str, dict[str, Any]]] = []
    for jsonl in sorted(reports_dir.glob("long_doc_leak.*.jsonl")):
        template_id = jsonl.stem[len("long_doc_leak."):]
        if "." in template_id:
            continue  # skip tagged snapshots
        agg = _load_aggregate(jsonl)
        if agg is None:
            print(f"  skipping {jsonl.name}: no _aggregate record")
            continue
        rows.append((_domain_of(template_id), template_id, agg))

    if not rows:
        raise SystemExit("no long_doc_leak reports found")

    total_pairs = sum(a["total_entity_turn_pairs"] for _, _, a in rows)
    total_leaked_pairs = sum(a["leaked_pairs"] for _, _, a in rows)
    total_tokens = sum(a["total_tokens"] for _, _, a in rows)
    total_leaked_tokens = sum(a["leaked_tokens"] for _, _, a in rows)
    total_sessions = sum(a["n_sessions"] for _, _, a in rows)
    activated = sum(a["n_chunker_activated"] for _, _, a in rows)
    chunks_failed = sum(a["n_chunks_failed_sessions"] for _, _, a in rows)
    seam_total = sum(a["seam_leaks_total"] for _, _, a in rows)
    seam_in_band = sum(a["seam_leaks_within_overlap"] for _, _, a in rows)
    cross_checked = sum(a["cross_path_alias_checked"] for _, _, a in rows)
    cross_carried = sum(a["cross_path_alias_carried"] for _, _, a in rows)
    cross_rate = cross_carried / cross_checked if cross_checked else None
    overall_p95 = max(
        (a["p95_turn_latency_ms"] for _, _, a in rows if a.get("p95_turn_latency_ms")),
        default=None,
    )

    lines = [
        f"# Cross-domain long-document leak summary — {args.date}",
        "",
        "Pipeline: ``sanitize_tool_output_chunked`` (tool-output path) for the "
        "long user turn, ``PrivacyRuntime.prepare_turn`` (input path) for the "
        "follow-up user turn, on Gemma 4 E2B via vLLM. Chunker: plaintext with "
        "max_chars=6000, overlap=300.",
        "",
        f"Aggregating {len(rows)} domain template(s).",
        "",
        "## Cross-domain headline",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Templates | {len(rows)} |",
        f"| Total sessions | {total_sessions} |",
        f"| Sessions where chunker activated (≥2 chunks) | {activated} ({activated / total_sessions:.0%}) |",
        f"| Sessions with at least one chunk failure | {chunks_failed} |",
        f"| Entity-turn pairs | {total_pairs} |",
        f"| Pair leaks | {total_leaked_pairs} |",
        f"| **Cross-domain pair leak** | **{_fmt_pct(total_leaked_pairs / total_pairs if total_pairs else 0)}** |",
        f"| Identifying tokens | {total_tokens} |",
        f"| Token leaks | {total_leaked_tokens} |",
        f"| **Cross-domain token leak** | **{_fmt_pct(total_leaked_tokens / total_tokens if total_tokens else 0)}** |",
        f"| Seam leaks (total tokens) | {seam_total} |",
        f"| Seam leaks within overlap band (300c) | {seam_in_band} ({seam_in_band / seam_total:.0%}) |"
        if seam_total
        else f"| Seam leaks within overlap band (300c) | {seam_in_band} |",
        f"| **Cross-path alias consistency (tool→input)** | **{_fmt_pct(cross_rate)}** ({cross_carried}/{cross_checked}) |",
        f"| p95 turn latency (worst across templates) | {_fmt_ms(overall_p95)} ms |",
        "",
        "## Per template",
        "",
        "| Domain | Template | Sessions | Chunker | Pair leak | Token leak | Seam (in band) | Cross-path alias |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for domain, template_id, agg in rows:
        seam_str = f"{agg['seam_leaks_total']} ({agg['seam_leaks_within_overlap']})"
        cross_str = (
            f"{_fmt_pct(agg['cross_path_alias_rate'])} "
            f"({agg['cross_path_alias_carried']}/{agg['cross_path_alias_checked']})"
        )
        lines.append(
            f"| `{domain}` | `{template_id}` | {agg['n_sessions']} | "
            f"{agg['n_chunker_activated']}/{agg['n_sessions']} | "
            f"{_fmt_pct(agg['pair_leak_rate'])} | "
            f"{_fmt_pct(agg['token_leak_rate'])} | "
            f"{seam_str} | {cross_str} |"
        )

    # Per-entity-type rollup across all long-doc templates.
    type_total_pairs: dict[str, int] = {}
    type_leaked_pairs: dict[str, int] = {}
    type_total_tokens: dict[str, int] = {}
    type_leaked_tokens: dict[str, int] = {}
    for _, _, agg in rows:
        for etype, n in agg.get("per_type_total_pairs", {}).items():
            type_total_pairs[etype] = type_total_pairs.get(etype, 0) + n
        for etype, n in agg.get("per_type_leaked_pairs", {}).items():
            type_leaked_pairs[etype] = type_leaked_pairs.get(etype, 0) + n
        for etype, n in agg.get("per_type_total_tokens", {}).items():
            type_total_tokens[etype] = type_total_tokens.get(etype, 0) + n
        for etype, n in agg.get("per_type_leaked_tokens", {}).items():
            type_leaked_tokens[etype] = type_leaked_tokens.get(etype, 0) + n

    lines.extend(
        [
            "",
            "## Per-entity-type recall (cross-domain)",
            "",
            "| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for etype in sorted(type_total_pairs):
        pair_total = type_total_pairs[etype]
        pair_leak = type_leaked_pairs.get(etype, 0)
        tok_total = type_total_tokens.get(etype, 0)
        tok_leak = type_leaked_tokens.get(etype, 0)
        pair_recall = 1.0 - pair_leak / pair_total if pair_total else 1.0
        tok_recall = 1.0 - tok_leak / tok_total if tok_total else 1.0
        lines.append(
            f"| `{etype}` | {_fmt_pct(pair_recall)} | {_fmt_pct(tok_recall)} | "
            f"{pair_total} | {pair_leak} | {tok_total} | {tok_leak} |"
        )

    out_path = reports_dir / "long_doc_cross_domain_summary.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path}")
    print(
        f"\nCross-domain pair leak: "
        f"{_fmt_pct(total_leaked_pairs / total_pairs if total_pairs else 0)}"
    )
    print(
        f"Cross-domain token leak: "
        f"{_fmt_pct(total_leaked_tokens / total_tokens if total_tokens else 0)}"
    )
    print(f"Chunker activated: {activated}/{total_sessions}")
    print(f"Seam leaks: {seam_total} ({seam_in_band} in overlap band)")
    print(f"Cross-path alias consistency: {_fmt_pct(cross_rate)}")


if __name__ == "__main__":
    main()
