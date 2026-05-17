from __future__ import annotations

from enum import Enum


class ToolPrivacyClass(str, Enum):
    LOCAL = "local"
    EXTERNAL = "external"
    SIDE_EFFECT = "side_effect"
