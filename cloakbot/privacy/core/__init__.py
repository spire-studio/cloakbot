"""Privacy core module exports."""

from __future__ import annotations

from cloakbot.privacy.core.detector import PiiDetector
from cloakbot.privacy.core.digit_detector import DigitPrivacyDetector
from cloakbot.privacy.core.general_detector import GeneralPrivacyDetector
from cloakbot.privacy.core.math_executer import (
    apply_privacy_math,
    build_math_execution_instruction,
)
from cloakbot.privacy.core.types import (
    REGISTRY,
    DetectedEntity,
    DetectionResult,
    Severity,
)

__all__ = [
    "REGISTRY",
    "DetectedEntity",
    "DetectionResult",
    "DigitPrivacyDetector",
    "GeneralPrivacyDetector",
    "PiiDetector",
    "Severity",
    "apply_privacy_math",
    "build_math_execution_instruction",
]
