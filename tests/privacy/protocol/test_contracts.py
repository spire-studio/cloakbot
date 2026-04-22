from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from cloakbot.privacy.protocol.contracts import (
    AgentTaskContract,
    ContractMeta,
    EventRecord,
    EventType,
    PrivacyStage,
    ProtocolStatus,
    ToolInvocationContract,
    TurnContract,
    TurnContextPayload,
)


def _meta() -> ContractMeta:
    return ContractMeta(
        trace_id="trace-1",
        span_id="span-1",
        session_id="session-1",
        turn_id="turn-1",
        idempotency_key="idem-1",
        timestamp=datetime.now(timezone.utc),
        status=ProtocolStatus.SUCCEEDED,
        error_code="",
    )


def test_turn_contract_requires_strict_fields() -> None:
    with pytest.raises(ValidationError):
        TurnContract.model_validate(
            {
                "meta": {
                    "trace_id": "trace-1",
                    "span_id": "span-1",
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "idempotency_key": "idem-1",
                    "timestamp": datetime.now(timezone.utc),
                    "status": "succeeded",
                    "error_code": "",
                    "extra": "forbidden",
                },
                "context": {
                    "intent": "chat",
                    "channel": "cli",
                    "privacy_stage": "raw",
                },
                "payload": {
                    "user_input": "hi",
                    "sanitized_input": None,
                    "agent_hint": None,
                },
            }
        )


def test_turn_contract_accepts_valid_payload() -> None:
    contract = TurnContract(
        meta=_meta(),
        context=TurnContextPayload(intent="chat", channel="cli", privacy_stage=PrivacyStage.RAW),
        payload={"user_input": "hello", "sanitized_input": None, "agent_hint": None},
    )

    dumped = contract.model_dump()
    assert dumped["context"]["privacy_stage"] == "raw"
    assert dumped["meta"]["status"] == "succeeded"


def test_agent_task_contract_mode_and_priority_literals() -> None:
    contract = AgentTaskContract(
        meta=_meta(),
        task={
            "task_id": "task-1",
            "task_type": "intent_analysis",
            "mode": "sync",
            "priority": "p0",
            "deadline_ms": 3000,
        },
        input={"data_ref": "inline"},
    )
    assert contract.task.mode == "sync"


def test_tool_invocation_contract_privacy_flags_required() -> None:
    with pytest.raises(ValidationError):
        ToolInvocationContract(
            meta=_meta(),
            tool={"name": "bash", "version": "1.0.0", "timeout_ms": 5000},
            input={"args": {}},
            privacy={},
        )


def test_event_record_has_versioned_taxonomy() -> None:
    event = EventRecord(
        event_type=EventType.TURN_RECEIVED,
        event_version="v1",
        trace_id="trace-1",
        span_id="span-1",
        session_id="session-1",
        turn_id="turn-1",
        stage=PrivacyStage.RAW,
        status=ProtocolStatus.STARTED,
        timestamp=datetime.now(timezone.utc),
        payload={"intent": "chat"},
    )
    assert event.event_type == EventType.TURN_RECEIVED
