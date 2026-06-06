"""Privacy-owned system-prompt fragments injected into the LLM.

Single home for every instruction the privacy layer adds to the model's system
prompt. Today that is the always-on "privacy mode" banner that teaches the model
to treat ``<<TYPE_N>>`` placeholders as the real (locally-restored) values rather
than refusing them as fake template variables.

Ownership boundary: the agent core stays privacy-agnostic. ``context.py`` exposes
a generic ``extra_sections`` seam and never imports privacy or inspects the vault;
this package decides *what*, *when*, and *whether* to inject. The off-switch is
``config.privacy.inject_system_prompt`` (always-on by default).
"""

from cloakbot.privacy.prompting.system_prompt import (
    build_privacy_system_section,
    privacy_mode_active,
)

__all__ = ["build_privacy_system_section", "privacy_mode_active"]
