"""
bot-core: Bot infrastructure with built-in AI and swappable adapters.

New pattern (AI built in, tools):
    from bot_core import BotRunner, BotConfig

    config = BotConfig(
        bot_name="Wrike Bot",
        version="1.0.0",
        system_prompt="You are a PM assistant...",
        tools=TOOLS,
        tool_executor=execute_tool,
    )
    BotRunner(config=config).start()

Legacy pattern (chat_fn injected):
    from bot_core import BotRunner, BotConfig

    BotRunner(config=config, chat_fn=my_chat_fn).start()
"""

from .runner import BotConfig, BotRunner
from .slack_adapter import SlackAdapter
from .scanner import get_bot_conversations, get_channel_history, get_channels_for_bot
from .utils import build_conversation_messages, get_thread_history, post_status_message
from .eval import EvalRunner, EvalCase, EvalReport, CaseResult

__all__ = [
    "BotRunner",
    "BotConfig",
    "SlackAdapter",
    "get_thread_history",
    "build_conversation_messages",
    "post_status_message",
    "get_channel_history",
    "get_channels_for_bot",
    "get_bot_conversations",
    "EvalRunner",
    "EvalCase",
    "EvalReport",
    "CaseResult",
]
__version__ = "0.5.0"
