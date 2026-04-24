from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cloakbot.config.paths import get_privacy_vault_dir
from cloakbot.privacy.core.state.vault import _safe_key
from cloakbot.privacy.webui.contracts import WebUIPrivacyPayload


def _turns_path(workspace: str | Path, session_key: str) -> Path:
    turns_dir = get_privacy_vault_dir(workspace) / "turns"
    turns_dir.mkdir(parents=True, exist_ok=True)
    return turns_dir / f"{_safe_key(session_key)}.jsonl"


def append_webui_privacy_payload(
    workspace: str | Path,
    session_key: str,
    payload: WebUIPrivacyPayload,
) -> None:
    path = _turns_path(workspace, session_key)
    line = payload.model_dump_json(by_alias=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_webui_privacy_payloads(
    workspace: str | Path,
    session_key: str,
) -> list[WebUIPrivacyPayload]:
    path = _turns_path(workspace, session_key)
    if not path.exists():
        return []

    payloads: list[WebUIPrivacyPayload] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payloads.append(WebUIPrivacyPayload.model_validate_json(line))
    return payloads


def replace_webui_privacy_payloads(
    workspace: str | Path,
    session_key: str,
    payloads: list[WebUIPrivacyPayload],
) -> None:
    path = _turns_path(workspace, session_key)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            for payload in payloads:
                tmp.write(json.dumps(payload.model_dump(mode="json", by_alias=True), ensure_ascii=False) + "\n")
        tmp_path.replace(path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise
