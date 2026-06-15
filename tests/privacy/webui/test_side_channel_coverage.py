"""Field-coverage invariant for the localhost egress redactors (webui-sec-001).

Each ``_redact_*`` in :mod:`cloakbot.privacy.webui.side_channel` hand-lists the
fields of its source model. If a new raw-bearing field is added to a contract and
the redactor is not updated, that field would ride out to a non-localhost client
unredacted. These tests pin the partition: every model field is classified as
either RAW (stripped by the redactor) or SAFE (preserved), the two sets cover
``model_fields`` exactly, and the redactor actually empties every RAW field.
"""

from __future__ import annotations

import pytest

from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import GeneralEntity, Severity
from cloakbot.privacy.tool_models import ToolApprovalStatus
from cloakbot.privacy.transparency.report import SessionEntityData
from cloakbot.privacy.webui.contracts import (
    WebUIToolApproval,
    WebUIUserAttachment,
    WebUIUserDocument,
)
from cloakbot.privacy.webui.side_channel import (
    _REDACTED_SENTINEL,
    _redact_annotation,
    _redact_attachment,
    _redact_document,
    _redact_entity,
    _redact_tool_approval,
)
from cloakbot.tool_privacy import ToolPrivacyClass

_ENTITY = SessionEntityData(
    placeholder="<<PERSON_1>>",
    entity_type="person",
    severity=Severity.HIGH,
    canonical="Alice Liang",
    aliases=["Alice"],
    value="Alice Liang",
    created_turn="t1",
    last_seen_turn="t2",
)
_ANNOTATION = RestoredTokenAnnotation(
    annotation_type="entity",
    placeholder="<<PERSON_1>>",
    text="Alice Liang",
    start=0,
    end=11,
    entity_type="person",
    severity=Severity.HIGH,
    canonical="Alice Liang",
    aliases=["Alice"],
    value="Alice Liang",
    formula="a + b",
)
_APPROVAL = WebUIToolApproval(
    approvalId="ap1",
    toolCallId="tc1",
    toolName="read_file",
    privacyClass=next(iter(ToolPrivacyClass)),
    remoteArguments={"path": "<<LOCAL_PATH_1>>"},
    restoredArguments={"path": "/home/alice/secret.txt"},
    detectedEntities=[GeneralEntity(text="/home/alice/secret.txt", entity_type="local_path")],
    status=next(iter(ToolApprovalStatus)),
)
_ATTACHMENT = WebUIUserAttachment(
    status="redacted",
    originalDataUrl="data:image/png;base64,RAWORIGINAL",
    redactedDataUrl="data:image/png;base64,SAFEREDACTED",
    redaction=None,
    reason="ok",
)
_DOCUMENT = WebUIUserDocument(
    documentName="d.txt",
    mimeType="text/plain",
    originalSha256="abc123",
    charCount=10,
    originalText="raw secret text",
    sanitizedText="<<PERSON_1>>",
    sanitizedPreview="<<PERSON_1>>",
    chunksTotal=1,
    chunksFailed=False,
    wasSanitized=True,
    entityTypes=["person"],
)

# (label, redactor, populated instance, model class, RAW fields, SAFE fields)
CASES = [
    (
        "entity",
        _redact_entity,
        _ENTITY,
        SessionEntityData,
        {"canonical", "aliases", "value"},
        {"placeholder", "entity_type", "severity", "created_turn", "last_seen_turn"},
    ),
    (
        "annotation",
        _redact_annotation,
        _ANNOTATION,
        RestoredTokenAnnotation,
        {"text", "canonical", "aliases", "value", "formula"},
        {"annotation_type", "placeholder", "start", "end", "entity_type", "severity"},
    ),
    (
        "tool_approval",
        _redact_tool_approval,
        _APPROVAL,
        WebUIToolApproval,
        {"restored_arguments", "detected_entities"},
        {
            "approval_id",
            "tool_call_id",
            "tool_name",
            "privacy_class",
            "remote_arguments",
            "status",
        },
    ),
    (
        "attachment",
        _redact_attachment,
        _ATTACHMENT,
        WebUIUserAttachment,
        {"original_data_url"},
        {"status", "redacted_data_url", "redaction", "reason"},
    ),
    (
        "document",
        _redact_document,
        _DOCUMENT,
        WebUIUserDocument,
        {"original_text"},
        {
            "document_name",
            "mime_type",
            "original_sha256",
            "char_count",
            "sanitized_text",
            "sanitized_preview",
            "chunks_total",
            "chunks_failed",
            "was_sanitized",
            "entity_types",
        },
    ),
]
_IDS = [case[0] for case in CASES]


def _emptied(value: object) -> bool:
    return value is None or value in ("", [], {}) or value == _REDACTED_SENTINEL


@pytest.mark.parametrize(("label", "redactor", "instance", "model_cls", "raw", "safe"), CASES, ids=_IDS)
def test_redactor_field_partition_is_total(label, redactor, instance, model_cls, raw, safe):
    fields = set(model_cls.model_fields)
    unclassified = fields - (raw | safe)
    assert not unclassified, (
        f"{model_cls.__name__} has unclassified field(s) {unclassified}; classify every new "
        "contract field as RAW (stripped) or SAFE (preserved) in side_channel before it can leak."
    )
    assert not (raw & safe), f"{model_cls.__name__} fields classified as both raw and safe: {raw & safe}"


@pytest.mark.parametrize(("label", "redactor", "instance", "model_cls", "raw", "safe"), CASES, ids=_IDS)
def test_redactor_strips_raw_and_preserves_safe(label, redactor, instance, model_cls, raw, safe):
    redacted = redactor(instance)
    for name in raw:
        assert _emptied(getattr(redacted, name)), f"{model_cls.__name__}.{name} was NOT stripped by the redactor"
    for name in safe:
        assert getattr(redacted, name) == getattr(instance, name), (
            f"{model_cls.__name__}.{name} was altered by the redactor (should be preserved verbatim)"
        )
