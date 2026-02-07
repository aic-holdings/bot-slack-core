"""
bot-core: Bot infrastructure with dependency-injected AI

Usage:
    from bot_core import BotRunner, BotConfig
    from artemis_client import ArtemisClient

    artemis = ArtemisClient(API_KEY)

    config = BotConfig(
        bot_name="MyBot",
        version="1.0.0",
        system_prompt="You are MyBot...",
    )
    runner = BotRunner(
        chat_fn=artemis.chat,
        config=config,
    )
    runner.start()
"""

from .runner import BotConfig, BotRunner
from .scanner import get_bot_conversations, get_channel_history, get_channels_for_bot
from .utils import build_conversation_messages, get_thread_history, post_status_message

__all__ = [
    "BotRunner",
    "BotConfig",
    "get_thread_history",
    "build_conversation_messages",
    "post_status_message",
    "get_channel_history",
    "get_channels_for_bot",
    "get_bot_conversations",
]
__version__ = "0.3.0"
