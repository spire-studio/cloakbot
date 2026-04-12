"""Chat channels module with plugin architecture."""

from cloakbot.channels.base import BaseChannel
from cloakbot.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
