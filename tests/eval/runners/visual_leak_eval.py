"""A2 lite — visual-side leak eval.

Loop, per seed:
  1. Render a synthetic invoice PNG with known PII (Faker → known GT bboxes).
  2. Feed the PNG to ``redact_visual_content_blocks`` with the GT spans
     as ``text_side_entities`` (so the redaction step has the same hand
     the text-side detector would have given it on a real document).
     The vLLM multimodal detector is *bypassed* so this measures
     "given the entities are known, does the redaction defeat re-OCR?"
     — a strictly weaker question than the production pipeline, but the
     only one that's reproducible offline.
  3. Re-OCR the redacted PNG with Tesseract.
  4. Score: how many GT strings (and how many GT tokens) survived
     visibly in the residual OCR output.

Metrics
-------
- spans_total                : count of GT spans across all renders
- spans_leaked               : GT spans whose full string still appears
                                in the redacted OCR text (case-sensitive
                                substring check; mirrors the A1 contract)
- spans_token_total          : GT spans broken into identifier tokens
                                (digits ≥3, alpha ≥4) — same rule as A1
- spans_token_leaked         : tokens that survived a re-OCR
- per_label                  : same breakdown grouped by GT ``label``
- box_count                  : how many redaction boxes were painted

Side artifacts (per seed):
  reports/<date>/visual/before.<template>.seed####.png
  reports/<date>/visual/after.<template>.seed####.png
  reports/<date>/visual/spans.<template>.seed####.json

Aggregate report:
  reports/<date>/visual.<template>.jsonl
  reports/<date>/visual.<template>.md

Usage
-----
    uv run python -m tests.eval.runners.visual_leak_eval --seeds 0 1 2 3 4

The runner imports ``cloakbot.privacy.visual_redaction`` and monkey-patches
``_inspect_visual`` to short-circuit the vLLM call. The patch is local to
this process — it does not affect the production pipeline.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pytesseract
from PIL import Image

from cloakbot.privacy import visual_redaction
from tests.eval.generators.render_invoice import (
    RenderedInvoice,
    render_invoice_v1,
    save_rendered_invoice,
)

DEFAULT_TEMPLATE = "invoice_v1"
REPORT_ROOT = Path("tests/eval/reports")


@dataclass
class SeedResult:
    template_id: str
    seed: int
    box_count: int
    labels: list[str]
    spans_total: int
    spans_leaked: int
    spans_token_total: int
    spans_token_leaked: int
    per_label: dict[str, dict[str, int]] = field(default_factory=dict)
    leaked_spans: list[dict[str, Any]] = field(default_factory=list)
    image_before: str = ""
    image_after: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AggregateResult:
    template_id: str
    n_seeds: int
    box_count_total: int
    spans_total: int
    spans_leaked: int
    spans_token_total: int
    spans_token_leaked: int
    per_label: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def span_leak_rate(self) -> float:
        return self.spans_leaked / self.spans_total if self.spans_total else 0.0

    @property
    def token_leak_rate(self) -> float:
        return self.spans_token_leaked / self.spans_token_total if self.spans_token_total else 0.0


# ---------------------------------------------------------------------------
# vLLM bypass
# ---------------------------------------------------------------------------


async def _stub_inspect_visual(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Replace ``_inspect_visual`` so the eval does not call vLLM.

    The text-side-entities path inside ``_redact_image`` is enough on its
    own to drive the redaction — we feed it the GT spans below.
    """
    return {"document_type": "invoice", "sensitive_items": []}


# ---------------------------------------------------------------------------
# Leak scoring
# ---------------------------------------------------------------------------


def _ident_tokens(value: str) -> list[str]:
    """Split a PII value into the identifier tokens we care about leaking.

    Same rule as the A1 text-leak eval so the two metrics are comparable:
    digit runs of length ≥3 and alpha runs of length ≥4.
    """
    tokens: list[str] = []
    for match in re.finditer(r"[A-Za-z]+|\d+", value):
        token = match.group(0)
        if token.isdigit() and len(token) >= 3:
            tokens.append(token)
        elif token.isalpha() and len(token) >= 4:
            tokens.append(token)
    return tokens


def _score_seed(
    invoice: RenderedInvoice,
    redacted_ocr_text: str,
) -> tuple[
    int,  # spans_leaked
    int,  # spans_token_total
    int,  # spans_token_leaked
    dict[str, dict[str, int]],
    list[dict[str, Any]],
]:
    spans_leaked = 0
    spans_token_total = 0
    spans_token_leaked = 0
    per_label: dict[str, dict[str, int]] = {}
    leaked_records: list[dict[str, Any]] = []

    for span in invoice.spans:
        slot_label = span.label
        bucket = per_label.setdefault(
            slot_label,
            {"spans": 0, "spans_leaked": 0, "tokens": 0, "tokens_leaked": 0},
        )
        bucket["spans"] += 1
        tokens = _ident_tokens(span.text)
        spans_token_total += len(tokens)
        bucket["tokens"] += len(tokens)

        span_appears = span.text and span.text in redacted_ocr_text
        if span_appears:
            spans_leaked += 1
            bucket["spans_leaked"] += 1

        leaked_tokens = [token for token in tokens if token in redacted_ocr_text]
        spans_token_leaked += len(leaked_tokens)
        bucket["tokens_leaked"] += len(leaked_tokens)

        if span_appears or leaked_tokens:
            leaked_records.append(
                {
                    "label": slot_label,
                    "text": span.text,
                    "leaked_full": bool(span_appears),
                    "leaked_tokens": leaked_tokens,
                }
            )

    return spans_leaked, spans_token_total, spans_token_leaked, per_label, leaked_records


# ---------------------------------------------------------------------------
# Per-seed run
# ---------------------------------------------------------------------------


async def _run_seed(seed: int, *, template: str, out_dir: Path) -> SeedResult:
    if template != DEFAULT_TEMPLATE:
        raise ValueError(f"only {DEFAULT_TEMPLATE!r} is supported in A2 lite (got {template!r})")

    invoice = render_invoice_v1(seed)

    # Persist the GT spans + raw render before redaction.
    before_path = save_rendered_invoice(
        invoice,
        out_dir,
    )
    before_path = before_path.rename(
        before_path.with_name(f"before.{invoice.template_id}.seed{seed:04d}.png")
    )
    (out_dir / f"spans.{invoice.template_id}.seed{seed:04d}.json").write_text(
        json.dumps(invoice.to_dict(), indent=2),
        encoding="utf-8",
    )

    # Build the content-blocks payload the visual pipeline consumes.
    image_b64 = base64.b64encode(invoice.image_bytes).decode("ascii")
    blocks = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            "_meta": {"path": before_path.name},
        },
    ]

    # Feed every GT span into the visual matcher as a text-side needle.
    text_side_entities = [
        (span.text, visual_redaction.text_entity_type_to_visual_label(span.entity_type))
        for span in invoice.spans
    ]

    redacted_blocks, _modified, records = await visual_redaction.redact_visual_content_blocks(
        blocks,
        placeholder_resolver=None,
        text_side_entities=text_side_entities,
    )

    # Extract the redacted PNG and persist it.
    redacted_bytes: bytes | None = None
    for block in redacted_blocks:
        if isinstance(block, dict) and block.get("type") == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
            if "," in url:
                redacted_bytes = base64.b64decode(url.split(",", 1)[1])
            break

    after_path = out_dir / f"after.{invoice.template_id}.seed{seed:04d}.png"
    box_count = 0
    labels_seen: list[str] = []
    if redacted_bytes is None:
        # Fail-closed: the pipeline omitted the image. Write a single-pixel
        # placeholder so the report path always exists.
        Image.new("RGB", (1, 1), color="white").save(after_path, format="PNG")
        redacted_ocr_text = ""
    else:
        after_path.write_bytes(redacted_bytes)
        with Image.open(BytesIO(redacted_bytes)) as opened:
            opened = opened.convert("RGB")
            redacted_ocr_text = pytesseract.image_to_string(opened) or ""

    for record in records:
        box_count += record.redaction_boxes
        labels_seen.extend(record.labels)

    spans_leaked, spans_token_total, spans_token_leaked, per_label, leaked_records = _score_seed(
        invoice, redacted_ocr_text
    )

    return SeedResult(
        template_id=invoice.template_id,
        seed=seed,
        box_count=box_count,
        labels=sorted(set(labels_seen)),
        spans_total=len(invoice.spans),
        spans_leaked=spans_leaked,
        spans_token_total=spans_token_total,
        spans_token_leaked=spans_token_leaked,
        per_label=per_label,
        leaked_spans=leaked_records,
        image_before=before_path.name,
        image_after=after_path.name,
    )


# ---------------------------------------------------------------------------
# Aggregation + report writing
# ---------------------------------------------------------------------------


def _aggregate(results: list[SeedResult], *, template_id: str) -> AggregateResult:
    agg = AggregateResult(
        template_id=template_id,
        n_seeds=len(results),
        box_count_total=0,
        spans_total=0,
        spans_leaked=0,
        spans_token_total=0,
        spans_token_leaked=0,
    )
    for seed_result in results:
        agg.box_count_total += seed_result.box_count
        agg.spans_total += seed_result.spans_total
        agg.spans_leaked += seed_result.spans_leaked
        agg.spans_token_total += seed_result.spans_token_total
        agg.spans_token_leaked += seed_result.spans_token_leaked
        for label, bucket in seed_result.per_label.items():
            slot = agg.per_label.setdefault(
                label,
                {"spans": 0, "spans_leaked": 0, "tokens": 0, "tokens_leaked": 0},
            )
            slot["spans"] += bucket["spans"]
            slot["spans_leaked"] += bucket["spans_leaked"]
            slot["tokens"] += bucket["tokens"]
            slot["tokens_leaked"] += bucket["tokens_leaked"]
    return agg


def _format_pct(part: int, whole: int) -> str:
    if whole == 0:
        return "n/a"
    return f"{part / whole * 100:.2f}%"


def _write_jsonl(path: Path, agg: AggregateResult, results: list[SeedResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "kind": "aggregate",
                    "template_id": agg.template_id,
                    "n_seeds": agg.n_seeds,
                    "box_count_total": agg.box_count_total,
                    "spans_total": agg.spans_total,
                    "spans_leaked": agg.spans_leaked,
                    "spans_token_total": agg.spans_token_total,
                    "spans_token_leaked": agg.spans_token_leaked,
                    "span_leak_rate": agg.span_leak_rate,
                    "token_leak_rate": agg.token_leak_rate,
                    "per_label": agg.per_label,
                }
            )
            + "\n"
        )
        for seed_result in results:
            f.write(
                json.dumps({"kind": "seed", **seed_result.to_dict()}, ensure_ascii=False) + "\n"
            )


def _write_markdown(path: Path, agg: AggregateResult, results: list[SeedResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# A2 visual leak eval — {agg.template_id}")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- **Seeds**: {agg.n_seeds}")
    lines.append(f"- **GT spans rendered**: {agg.spans_total}")
    lines.append(f"- **Redaction boxes painted**: {agg.box_count_total}")
    lines.append(
        f"- **Span leak**: {agg.spans_leaked} / {agg.spans_total} "
        f"= **{_format_pct(agg.spans_leaked, agg.spans_total)}**"
    )
    lines.append(
        f"- **Token leak**: {agg.spans_token_leaked} / {agg.spans_token_total} "
        f"= **{_format_pct(agg.spans_token_leaked, agg.spans_token_total)}**"
    )
    lines.append("")
    lines.append("## Per-label breakdown")
    lines.append("")
    lines.append("| Label | Spans | Span leak | Tokens | Token leak |")
    lines.append("|---|---:|---:|---:|---:|")
    for label in sorted(agg.per_label.keys()):
        bucket = agg.per_label[label]
        span_leak = _format_pct(bucket["spans_leaked"], bucket["spans"])
        token_leak = _format_pct(bucket["tokens_leaked"], bucket["tokens"])
        lines.append(
            f"| {label} | {bucket['spans']} | {span_leak} | {bucket['tokens']} | {token_leak} |"
        )
    lines.append("")
    lines.append("## Per-seed")
    lines.append("")
    lines.append("| Seed | Boxes | Spans | Span leak | Tokens | Token leak | Before | After |")
    lines.append("|---:|---:|---:|---:|---:|---:|---|---|")
    for seed_result in results:
        span_leak = _format_pct(seed_result.spans_leaked, seed_result.spans_total)
        token_leak = _format_pct(seed_result.spans_token_leaked, seed_result.spans_token_total)
        lines.append(
            "| {seed} | {boxes} | {spans} | {span_leak} | {tokens} | {token_leak} | "
            "`{before}` | `{after}` |".format(
                seed=seed_result.seed,
                boxes=seed_result.box_count,
                spans=seed_result.spans_total,
                span_leak=span_leak,
                tokens=seed_result.spans_token_total,
                token_leak=token_leak,
                before=seed_result.image_before,
                after=seed_result.image_after,
            )
        )
    lines.append("")
    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "- vLLM multimodal detector is **bypassed**; redaction is driven by "
        "ground-truth text spans fed in via `text_side_entities`. So this "
        "evaluates the redaction + re-OCR contract, not the detector's recall."
    )
    lines.append(
        "- Span leak = the GT string still appears verbatim in the redacted "
        "image after re-OCR. Token leak = a digit run ≥3 or alpha run ≥4 from "
        "the GT survives — same rule as A1."
    )
    lines.append(
        "- Before/after PNGs land alongside this report so each row is "
        "auditable visually."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _main(args: argparse.Namespace) -> int:
    # Local monkey-patch — does not affect anything outside this process.
    visual_redaction._inspect_visual = _stub_inspect_visual  # type: ignore[attr-defined]

    today = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    image_dir = REPORT_ROOT / today / "visual"
    image_dir.mkdir(parents=True, exist_ok=True)

    results: list[SeedResult] = []
    for seed in args.seeds:
        result = await _run_seed(seed, template=args.template, out_dir=image_dir)
        results.append(result)
        print(
            f"seed={seed:>3}  boxes={result.box_count:>3}  "
            f"spans={result.spans_leaked}/{result.spans_total}  "
            f"tokens={result.spans_token_leaked}/{result.spans_token_total}"
        )

    agg = _aggregate(results, template_id=args.template)
    jsonl_path = REPORT_ROOT / today / f"visual.{args.template}.jsonl"
    md_path = REPORT_ROOT / today / f"visual.{args.template}.md"
    _write_jsonl(jsonl_path, agg, results)
    _write_markdown(md_path, agg, results)
    print(f"\nwrote {jsonl_path}")
    print(f"wrote {md_path}")
    print(
        f"\nspan_leak={agg.spans_leaked}/{agg.spans_total} "
        f"({_format_pct(agg.spans_leaked, agg.spans_total)})  "
        f"token_leak={agg.spans_token_leaked}/{agg.spans_token_total} "
        f"({_format_pct(agg.spans_token_leaked, agg.spans_token_total)})"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="A2 lite visual leak eval")
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[0, 1, 2, 3, 4],
        help="seeds to render (default: 0..4)",
    )
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    parser.add_argument(
        "--date",
        default=None,
        help="override the date dir under reports/ (default: today UTC)",
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
