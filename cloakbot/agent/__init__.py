"""Agent core module."""

from cloakbot.agent.context import ContextBuilder
from cloakbot.agent.hook import AgentHook, AgentHookContext, CompositeHook
from cloakbot.agent.loop import AgentLoop
from cloakbot.agent.memory import Dream, MemoryStore
from cloakbot.agent.skills import SkillsLoader
from cloakbot.agent.subagent import SubagentManager

__all__ = [
    "AgentHook",
    "AgentHookContext",
    "AgentLoop",
    "CompositeHook",
    "ContextBuilder",
    "Dream",
    "MemoryStore",
    "SkillsLoader",
    "SubagentManager",
]
