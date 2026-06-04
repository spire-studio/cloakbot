"""Additive HTTP route: ``GET /api/sessions/{key}/privacy``.

History rehydration for the privacy overlay. Returns the per-turn
:class:`WebUIPrivacyPayload` log persisted under the session vault, **gated by the
same blocking localhost check** as the WS side-channel: a localhost connection
gets the full raw-bearing payloads, any non-localhost connection gets the redacted
projection (placeholders + entity types/severities/counts only).

This module is intentionally transport-thin and side-effect-free so it can be
unit-tested without the full gateway; ``handle_privacy_route`` takes the already
parsed dependencies and returns a websockets ``Response`` (or ``None`` to signal
"not my route" so the caller falls through to the next dispatcher).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger
from websockets.http11 import Response

from cloakbot.privacy.webui.history import load_webui_privacy_payloads
from cloakbot.privacy.webui.side_channel import project_payload_for_egress
from cloakbot.webui.http_utils import http_error as _http_error
from cloakbot.webui.http_utils import http_json_response as _http_json_response
from cloakbot.webui.http_utils import is_localhost as _is_localhost

_PRIVACY_ROUTE_RE = re.compile(r"^/api/sessions/([^/]+)/privacy$")


def is_privacy_route(path: str) -> bool:
    """True when *path* (already stripped of query) is the privacy history route."""
    return _PRIVACY_ROUTE_RE.match(path) is not None


def handle_privacy_route(
    *,
    connection: Any,
    got: str,
    workspace: str | Path,
    decode_key: Callable[[str], str | None],
    is_websocket_session_key: Callable[[str], bool],
    check_api_token: Callable[[], bool],
) -> Response | None:
    """Serve ``GET /api/sessions/{key}/privacy`` with the localhost egress gate.

    Returns ``None`` when *got* is not the privacy route so the caller can fall
    through to its next dispatcher.
    """
    m = _PRIVACY_ROUTE_RE.match(got)
    if not m:
        return None

    if not check_api_token():
        return _http_error(401, "Unauthorized")

    decoded_key = decode_key(m.group(1))
    if decoded_key is None:
        return _http_error(400, "invalid session key")
    if not is_websocket_session_key(decoded_key):
        return _http_error(404, "session not found")

    try:
        payloads = load_webui_privacy_payloads(workspace, decoded_key)
    except Exception as exc:  # corrupt jsonl line / IO error
        logger.warning("privacy history load failed for {}: {}", decoded_key, exc)
        return _http_error(500, "failed to load privacy history")

    localhost = _is_localhost(connection)
    turns = [
        project_payload_for_egress(payload, is_localhost=localhost).model_dump(
            mode="json", by_alias=True
        )
        for payload in payloads
    ]
    return _http_json_response({"turns": turns, "localhost": localhost})
