"""Label/tag translation tables shared across the visual pipeline.

Two leaf lookups with no other in-package dependencies:

* :func:`visual_label_to_tag` maps a *visual detector label* (``customer_name``)
  to a *privacy-registry tag* (``PERSON``) so a box detected in an image shares
  the same vault placeholder family as a free-text ``person`` detection
  elsewhere in the same session.
* :func:`text_entity_type_to_visual_label` is the inverse direction, used when
  forwarding text-side entities into the visual matcher so the bbox a text-only
  catch produces carries a label the rest of the visual pipeline can route on.
"""

from __future__ import annotations

# Visual detector labels → privacy-registry tags. Used by the
# placeholder resolver so a box detected as ``customer_name`` ends up
# sharing the same vault placeholder family as a free-text ``person``
# detection elsewhere in the same session.
_VISUAL_LABEL_TO_TAG: dict[str, str] = {
    "vendor_name": "ORG",
    "customer_name": "PERSON",
    "billing_address": "ADDRESS",
    "shipping_address": "ADDRESS",
    "email": "EMAIL",
    "phone": "PHONE",
    "tax_id": "ID",
    "invoice_number": "ID",
    "account_number": "ID",
    "bank_info": "ID",
    "transaction_id": "ID",
    "payment_gateway": "ORG",
    "service_code": "ID",
    "date": "DATE",
    "amount": "FINANCE",
    "line_item": "FINANCE",
    "other": "ENTITY",
}

# Inverse mapping: text-detector entity slug → preferred visual label.
# Used when forwarding text-side entities into the visual matcher so
# the bbox a text-only catch ends up with carries a label the rest of
# the visual pipeline can route on (region map, vault tag).
_TEXT_ENTITY_TYPE_TO_VISUAL_LABEL: dict[str, str] = {
    "person": "customer_name",
    "org": "vendor_name",
    "address": "billing_address",
    "email": "email",
    "phone": "phone",
    "identifier": "transaction_id",
    "url": "service_code",
    "local_path": "service_code",
    "credential": "other",
    "medical": "other",
    "ip_address": "other",
    "temporal": "date",
    "financial": "amount",
    "percentage": "amount",
    "amount": "amount",
    "measurement": "amount",
    "value": "amount",
}


def text_entity_type_to_visual_label(entity_type: str) -> str:
    return _TEXT_ENTITY_TYPE_TO_VISUAL_LABEL.get(entity_type, "other")


def visual_label_to_tag(label: str) -> str:
    """Map a visual detector label to a privacy-registry tag, default ``ENTITY``."""
    return _VISUAL_LABEL_TO_TAG.get(label, "ENTITY")


__all__ = [
    "text_entity_type_to_visual_label",
    "visual_label_to_tag",
]
