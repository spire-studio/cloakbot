# A2 visual leak eval — invoice_v1

_Generated 2026-05-15 10:11 UTC_

## Headline

- **Seeds**: 10
- **GT spans rendered**: 180
- **Redaction boxes painted**: 204
- **Span leak**: 2 / 180 = **1.11%**
- **Token leak**: 4 / 395 = **1.01%**

## Per-label breakdown

| Label | Spans | Span leak | Tokens | Token leak |
|---|---:|---:|---:|---:|
| account_number | 20 | 0.00% | 60 | 0.00% |
| amount | 50 | 0.00% | 50 | 0.00% |
| billing_address | 20 | 0.00% | 123 | 0.00% |
| customer_name | 10 | 0.00% | 20 | 0.00% |
| date | 20 | 0.00% | 20 | 0.00% |
| email | 20 | 5.00% | 43 | 6.98% |
| invoice_number | 10 | 0.00% | 10 | 0.00% |
| phone | 10 | 0.00% | 30 | 0.00% |
| transaction_id | 10 | 0.00% | 20 | 0.00% |
| vendor_name | 10 | 10.00% | 19 | 5.26% |

## Per-seed

| Seed | Boxes | Spans | Span leak | Tokens | Token leak | Before | After |
|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 22 | 18 | 0.00% | 41 | 0.00% | `before.invoice_v1.seed0000.png` | `after.invoice_v1.seed0000.png` |
| 1 | 19 | 18 | 5.56% | 40 | 5.00% | `before.invoice_v1.seed0001.png` | `after.invoice_v1.seed0001.png` |
| 2 | 19 | 18 | 0.00% | 40 | 0.00% | `before.invoice_v1.seed0002.png` | `after.invoice_v1.seed0002.png` |
| 3 | 22 | 18 | 0.00% | 41 | 0.00% | `before.invoice_v1.seed0003.png` | `after.invoice_v1.seed0003.png` |
| 4 | 19 | 18 | 5.56% | 36 | 2.78% | `before.invoice_v1.seed0004.png` | `after.invoice_v1.seed0004.png` |
| 5 | 20 | 18 | 0.00% | 38 | 0.00% | `before.invoice_v1.seed0005.png` | `after.invoice_v1.seed0005.png` |
| 6 | 22 | 18 | 0.00% | 41 | 0.00% | `before.invoice_v1.seed0006.png` | `after.invoice_v1.seed0006.png` |
| 7 | 20 | 18 | 0.00% | 39 | 0.00% | `before.invoice_v1.seed0007.png` | `after.invoice_v1.seed0007.png` |
| 8 | 21 | 18 | 0.00% | 39 | 2.56% | `before.invoice_v1.seed0008.png` | `after.invoice_v1.seed0008.png` |
| 9 | 20 | 18 | 0.00% | 40 | 0.00% | `before.invoice_v1.seed0009.png` | `after.invoice_v1.seed0009.png` |

## How to read this

- vLLM multimodal detector is **bypassed**; redaction is driven by ground-truth text spans fed in via `text_side_entities`. So this evaluates the redaction + re-OCR contract, not the detector's recall.
- Span leak = the GT string still appears verbatim in the redacted image after re-OCR. Token leak = a digit run ≥3 or alpha run ≥4 from the GT survives — same rule as A1.
- Before/after PNGs land alongside this report so each row is auditable visually.
