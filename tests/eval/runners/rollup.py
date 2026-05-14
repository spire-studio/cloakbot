"""Roll up per-template ``text_leak.*.jsonl`` reports into one cross-domain table.

Run after every template's ``text_leak_eval`` invocation has produced its
own JSONL. Reads the final ``_aggregate`` record from each file and emits
a single markdown summary so the writeup can quote one consolidated number
per domain.

Usage:
    python -m tests.eval.runners.rollup [--date 2026-05-14]
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
    # Best-effort domain extraction from the template id naming convention.
    if template_id.startswith("medical"):
        return "medical"
    if template_id.startswith("hr"):
        return "hr"
    if template_id.startswith("finance"):
        return "finance"
    if template_id.startswith("customer_service"):
        return "customer_service"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--reports-dir", type=Path, default=None)
    args = parser.parse_args()

    reports_dir = args.reports_dir or REPO_ROOT / "tests/eval/reports" / args.date
    if not reports_dir.exists():
        raise SystemExit(f"no reports directory at {reports_dir}")

    domain_aggregates: list[tuple[str, str, dict[str, Any]]] = []
    for jsonl in sorted(reports_dir.glob("text_leak.*.jsonl")):
        # Skip A/B snapshots — anything with a tag suffix after the
        # template id (e.g. ``text_leak.<template>.pre_org_fix.jsonl``)
        # or with a legacy bare tag (``baseline``, ``post_refactor_*``).
        # Real per-template reports look like ``text_leak.<template>.jsonl``
        # with no extra dots in the template id segment.
        stem = jsonl.stem  # "text_leak.<template_id>" or "text_leak.<id>.<tag>"
        template_id = stem[len("text_leak."):]
        if "." in template_id:
            continue
        if template_id in {"baseline", "post_refactor_1seed", "post_refactor_4seeds"}:
            continue
        agg = _load_aggregate(jsonl)
        if agg is None:
            print(f"  skipping {jsonl.name}: no _aggregate record")
            continue
        domain = _domain_of(template_id)
        domain_aggregates.append((domain, template_id, agg))

    if not domain_aggregates:
        raise SystemExit("no per-template reports found")

    # Cross-domain rollup
    total_pairs = sum(a["total_entity_turn_pairs"] for _, _, a in domain_aggregates)
    total_leaked_pairs = sum(a["leaked_pairs"] for _, _, a in domain_aggregates)
    total_tokens = sum(a["total_tokens"] for _, _, a in domain_aggregates)
    total_leaked_tokens = sum(a["leaked_tokens"] for _, _, a in domain_aggregates)
    multi_turn_total = sum(a["multi_turn_entities_total"] for _, _, a in domain_aggregates)
    multi_turn_consistent_weighted = sum(
        a["multi_turn_entities_total"] * a["alias_consistency_across_turns"]
        for _, _, a in domain_aggregates
        if a["alias_consistency_across_turns"] is not None
    )
    overall_alias = (
        multi_turn_consistent_weighted / multi_turn_total if multi_turn_total else None
    )
    overall_p95 = max(
        (a["p95_turn_latency_ms"] for _, _, a in domain_aggregates if a.get("p95_turn_latency_ms")),
        default=None,
    )

    lines = [
        f"# Cross-domain text leak summary — {args.date}",
        "",
        f"Pipeline: ``PrivacyRuntime.prepare_turn`` on Gemma 4 E2B via vLLM.",
        f"Aggregating {len(domain_aggregates)} domain template(s).",
        "",
        "## Cross-domain headline",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Domains | {len({d for d, _, _ in domain_aggregates})} |",
        f"| Total sessions | {sum(a['n_sessions'] for _, _, a in domain_aggregates)} |",
        f"| Total entity-turn pairs | {total_pairs} |",
        f"| Pair leaks | {total_leaked_pairs} |",
        f"| **Cross-domain pair leak** | **{_fmt_pct(total_leaked_pairs / total_pairs if total_pairs else 0)}** |",
        f"| Identifying tokens | {total_tokens} |",
        f"| Token leaks | {total_leaked_tokens} |",
        f"| **Cross-domain token leak** | **{_fmt_pct(total_leaked_tokens / total_tokens if total_tokens else 0)}** |",
        f"| Multi-turn recurring entities | {multi_turn_total} |",
        f"| **Cross-domain alias consistency** | **{_fmt_pct(overall_alias)}** |",
        f"| p95 turn latency (worst across domains) | {_fmt_ms(overall_p95)} ms |",
        "",
        "## Per domain",
        "",
        "| Domain | Template | Sessions | Pairs | Pair leak | Token leak | Alias | p95 (ms) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for domain, template_id, agg in domain_aggregates:
        lines.append(
            f"| `{domain}` | `{template_id}` | {agg['n_sessions']} | "
            f"{agg['total_entity_turn_pairs']} | "
            f"{_fmt_pct(agg['pair_leak_rate'])} | "
            f"{_fmt_pct(agg['token_leak_rate'])} | "
            f"{_fmt_pct(agg['alias_consistency_across_turns'])} | "
            f"{_fmt_ms(agg['p95_turn_latency_ms'])} |"
        )

    # Per-entity-type rollup across all domains
    type_total_pairs: dict[str, int] = {}
    type_leaked_pairs: dict[str, int] = {}
    type_total_tokens: dict[str, int] = {}
    type_leaked_tokens: dict[str, int] = {}
    for _, _, agg in domain_aggregates:
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

    out_path = reports_dir / "cross_domain_summary.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path}")
    print(f"\nCross-domain pair leak: {_fmt_pct(total_leaked_pairs / total_pairs if total_pairs else 0)}")
    print(
        f"Cross-domain token leak: "
        f"{_fmt_pct(total_leaked_tokens / total_tokens if total_tokens else 0)}"
    )
    print(f"Cross-domain alias consistency: {_fmt_pct(overall_alias)}")


if __name__ == "__main__":
    main()
