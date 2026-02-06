"""
slack-bot-core: Shared Slack bot utilities with dependency-injected AI

Usage:
    from slack_bot_core import SlackBotRunner
    from artemis_client import ArtemisClient

    artemis = ArtemisClient(API_KEY)

    runner = SlackBotRunner(
        system_prompt="You are MyBot...",
        chat_fn=artemis.chat,
        status_channel="C08B64J5G7N",
    )
    runner.start()
"""

from .runner import SlackBotRunner
from .utils import get_thread_history, build_conversation_messages, post_status_message
from .scanner import get_channel_history, get_channels_for_bot, get_bot_conversations

__all__ = [
    "SlackBotRunner",
    "get_thread_history",
    "build_conversation_messages",
    "post_status_message",
    "get_channel_history",
    "get_channels_for_bot",
    "get_bot_conversations",
]
__version__ = "0.2.0"
