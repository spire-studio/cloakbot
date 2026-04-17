from __future__ import annotations

from dataclasses import dataclass
from cloakbot.privacy.hooks.context import TurnContext


@dataclass
class TurnReport:
    ctx: TurnContext

    def render(self) -> str:
        """Produce a stylized 🔒 Privacy Report."""
        user_input_entities = self.ctx.user_input_entities
        tool_output_entities = self.ctx.tool_output_entities

        if not any([user_input_entities, tool_output_entities]):
            return ""

        # Using Markdown syntax that Rich renders with colors/styles
        lines = ["### 🔒 Privacy Report  "]

        if user_input_entities:
            lines.append(f"├─ **{len(user_input_entities)}** entities masked in input:  ")
            lines.append(f"│  > {_summarize(user_input_entities)}  ")

        if tool_output_entities:
            lines.append(f"├─ **{len(tool_output_entities)}** entities caught in tool output:  ")
            lines.append(f"│  > {_summarize(tool_output_entities)}  ")

        status = "_✓ all tokens restored_" if self.ctx.was_sanitized else "_✓ no restoration needed_"
        lines.append(f"└─ {status}")

        return "\n".join(lines)


def _summarize(entities) -> str:
    """Style entities with inline code blocks for color variety."""
    # Group by type to keep it short
    counts = {}
    for e in entities:
        key = f"`{e.entity_type.upper()}` ({e.severity.value})"
        counts[key] = counts.get(key, 0) + 1
    
    return ", ".join(
        f"{key} x{val}" if val > 1 else key 
        for key, val in counts.items()
    )
