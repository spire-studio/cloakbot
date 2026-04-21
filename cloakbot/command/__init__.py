"""Slash command routing and built-in handlers."""

from cloakbot.command.builtin import register_builtin_commands
from cloakbot.command.router import CommandContext, CommandRouter

__all__ = ["CommandContext", "CommandRouter", "register_builtin_commands"]
