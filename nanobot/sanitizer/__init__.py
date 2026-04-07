"""CloakBot sanitizer — local PII detection and placeholder rewriting."""

from nanobot.sanitizer.sanitize import remap_response, sanitize_input

__all__ = ["sanitize_input", "remap_response"]
