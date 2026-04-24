from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import emit_event, get_event_sink
from cloakbot.privacy.webui import build_webui_privacy_payload


def test_build_webui_privacy_payload_includes_turn_and_timeline() -> None:
    get_event_sink().clear()
    ctx = TurnContext(
        session_key="webui:session-1",
        turn_id="turn-1",
        raw_input="hello Alice",
        sanitized_input="hello <<PERSON_1>>",
    )

    emit_event(
        event_type=EventType.TURN_SANITIZE_SUCCEEDED,
        trace_id=f"{ctx.session_key}:{ctx.turn_id}",
        span_id="turn-1:sanitize:completed",
        parent_span_id="turn-1:sanitize",
        session_id=ctx.session_key,
        turn_id=ctx.turn_id,
        stage=PrivacyStage.SANITIZED,
        status=ProtocolStatus.SUCCEEDED,
        payload={"was_sanitized": True},
    )

    payload = build_webui_privacy_payload(ctx.session_key, ctx).model_dump(mode="json", by_alias=True)

    assert payload["privacyTurn"]["turnId"] == "turn-1"
    assert payload["privacyTurn"]["remotePrompt"] == "hello <<PERSON_1>>"
    assert payload["privacyTimeline"]["turnId"] == "turn-1"
    assert payload["privacyTimeline"]["events"][0]["eventType"] == "turn.sanitize.succeeded"
    assert payload["privacyTimeline"]["events"][0]["payload"] == {"was_sanitized": True}
