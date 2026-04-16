"""Privacy token restoration helpers."""

from __future__ import annotations

import re

from cloakbot.privacy.core.vault import PLACEHOLDER_RE, _SessionMap


def restore_tokens(text: str, smap: _SessionMap) -> str:
    """
    Replace every ``<<TOKEN>>`` placeholder in *text* with its original value
    in a single regex pass.

    A single ``re.sub`` call with a lookup callback eliminates ordering issues
    (e.g. ``<<PERSON_10>>`` vs ``<<PERSON_1>>``) and avoids the corruption
    problems inherent in iterative ``str.replace`` approaches.
    """
    if not smap.placeholder_to_original:
        return text

    def _replace(m: re.Match) -> str:
        token = m.group(0)  # e.g. "<<PERSON_1>>"
        return smap.placeholder_to_original.get(token, token)

    return PLACEHOLDER_RE.sub(_replace, text)
