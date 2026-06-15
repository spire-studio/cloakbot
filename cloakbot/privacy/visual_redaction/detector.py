"""Remote visual detector: prompt, multimodal call, and JSON parsing.

This is the only submodule that talks to the (local-network) detector model. It
builds the high-recall invoice prompt, issues the ``chat.completions`` call with
the image, and parses the model's JSON reply into a plain dict the pipeline can
consume.

The detector never makes a redaction decision on its own: it only proposes
``sensitive_items``. The pipeline confirms each item against local OCR before a
box is drawn, and fails closed when it cannot — so a hallucinated or truncated
detector reply can never cause raw PII to be forwarded.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from json_repair import repair_json

from cloakbot.providers.detector import get_detector_client, get_detector_model

_SYSTEM_PROMPT = """You are a local privacy inspector for invoices and financial documents.

You will receive one document page image. Identify privacy-sensitive visible text
that must be redacted before the page is sent to an untrusted remote LLM.

Return ONLY valid JSON with this schema:
{
  "document_type": "invoice|receipt|statement|other",
  "sensitive_items": [
    {
      "label": "vendor_name|customer_name|billing_address|shipping_address|email|phone|tax_id|invoice_number|account_number|bank_info|transaction_id|payment_gateway|service_code|date|amount|line_item|other",
      "text": "exact visible text if readable",
      "reason": "why this is sensitive",
      "confidence": 0.0
    }
  ]
}

Prefer high recall for invoices: names, addresses, emails, account IDs, invoice
numbers, transaction IDs, dates, money amounts, and line item details can all be
sensitive in private documents.

Additional recall hints — DO extract these (they are private when attached to a
specific customer's document, even though the brand names themselves are public):

  * payment_gateway: Alipay, WeChat Pay, UnionPay, Stripe, PayPal, Square,
    Adyen, Braintree, ApplePay, GooglePay, and similar processor names that
    appear next to a transaction. Their presence reveals the customer's payment
    relationship.
  * service_code: internal service / product / instance identifiers that look
    like "LAX.AN4.Pro.TINY", "DMIT-US-1", "us-west-2-i-0a1b2c3d", or any
    dot/hyphen-separated alphanumeric code in a line item or description.
  * transaction_id: long compound IDs (>= 16 chars), including those joined by
    "|", "-", "_", or "." separators — extract the *entire* span as one item.
  * date: every visible date on the page (issue date, transaction date,
    billing period start/end, due date). Do not skip "templated"-looking dates.
"""


async def _inspect_visual(raw: bytes, *, mime: str, image_size: tuple[int, int]) -> dict[str, Any]:
    client = get_detector_client()
    width, height = image_size
    response = await client.chat.completions.create(
        model=get_detector_model(),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Inspect this document page for sensitive visible information. "
                            f"Image size: width={width}px, height={height}px."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                        },
                    },
                ],
            },
        ],
        temperature=0,
        max_tokens=2048,
        stream=False,
        response_format={"type": "json_object"},
    )
    raw_text = response.choices[0].message.content or "{}"
    return _parse_model_json(raw_text)


def _parse_model_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = json.loads(repair_json(cleaned))
    return parsed if isinstance(parsed, dict) else {}


__all__ = [
    "_inspect_visual",
    "_parse_model_json",
]
