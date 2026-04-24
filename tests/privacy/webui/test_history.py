from pathlib import Path

from cloakbot.privacy.transparency.report import SessionPrivacySnapshot
from cloakbot.privacy.webui import (
    WebUIPrivacyPayload,
    WebUIPrivacyTimeline,
    WebUIPrivacyTurn,
)
from cloakbot.privacy.webui.history import (
    append_webui_privacy_payload,
    load_webui_privacy_payloads,
)


def test_webui_privacy_history_round_trips_payloads(tmp_path: Path) -> None:
    payload = WebUIPrivacyPayload(
        privacy=SessionPrivacySnapshot(total_entities=0),
        privacyAnnotations=[],
        privacyTurn=WebUIPrivacyTurn(
            turnId="turn-1",
            intent="chat",
            remotePrompt="hello <<PERSON_1>>",
            localComputations=[],
        ),
        privacyTimeline=WebUIPrivacyTimeline(
            turnId="turn-1",
            traceId="trace-1",
            totalDurationMs=0,
            stageDurationsMs={},
            events=[],
        ),
    )

    append_webui_privacy_payload(tmp_path, "webui:session-1", payload)

    loaded = load_webui_privacy_payloads(tmp_path, "webui:session-1")

    assert len(loaded) == 1
    assert loaded[0].privacy_turn.turn_id == "turn-1"
    assert loaded[0].privacy_turn.remote_prompt == "hello <<PERSON_1>>"
