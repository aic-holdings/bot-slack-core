"""
BotRunner — Core bot orchestrator.

The runner owns:
- AI client (OpenRouter, built-in)
- Message processing (diagnostics, tool-use loop, simple chat)
- Bot configuration (identity, system prompt, tools)

The adapter (e.g., SlackAdapter) owns the human interface.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .ai import OpenRouterClient

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration for a bot.

    Required:
        bot_name: Bot display name (also used for OpenRouter X-Title attribution)
        version: Version string
        system_prompt: AI system prompt

    AI options:
        model: OpenRouter model ID (default: anthropic/claude-sonnet-4)
        tools: OpenRouter tool definitions for function calling
        tool_executor: Function (tool_name, tool_args) -> result

    Optional:
        status_channel: Slack channel ID for status messages
        diagnostic_commands: Commands that trigger diagnostic info
    """

    bot_name: str
    version: str
    system_prompt: str
    model: str = "anthropic/claude-sonnet-4"
    tools: Optional[List[Dict]] = None
    tool_executor: Optional[Callable[[str, Dict], Any]] = None
    status_channel: Optional[str] = None
    diagnostic_commands: List[str] = field(
        default_factory=lambda: [
            "status", "info", "diag", "diagnostics", "version", "health", "ping"
        ]
    )


class BotRunner:
    """
    Core bot orchestrator with built-in AI.

    New pattern (AI built in):
        config = BotConfig(
            bot_name="Wrike Bot",
            system_prompt="You are a PM assistant...",
            tools=TOOLS,
            tool_executor=execute_tool,
        )
        BotRunner(config=config).start()

    Legacy pattern (chat_fn injected, for migration):
        BotRunner(config=config, chat_fn=my_chat_fn).start()
    """

    def __init__(
        self,
        config: BotConfig,
        adapter=None,
        chat_fn: Optional[Callable[[List[Dict], Optional[str]], str]] = None,
    ):
        self.config = config
        self.chat_fn = chat_fn
        self._start_time = 0.0

        # Built-in AI (unless using legacy chat_fn)
        if not chat_fn:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("Missing OPENROUTER_API_KEY")
            self.ai = OpenRouterClient(
                api_key=api_key,
                bot_name=config.bot_name,
                model=config.model,
            )
        else:
            self.ai = None

        # Default to Slack adapter (lazy import avoids requiring tokens at import time)
        if adapter is not None:
            self.adapter = adapter
        else:
            from .slack_adapter import SlackAdapter

            self.adapter = SlackAdapter()

    def handle_message(self, user_text: str, messages: List[Dict]) -> str:
        """
        Process a message. Called by the adapter.

        Args:
            user_text: Raw user text (for diagnostic command detection)
            messages: Conversation as LLM messages [{"role": ..., "content": ...}]

        Returns:
            Response string
        """
        if user_text.lower() in self.config.diagnostic_commands:
            return self._get_diagnostic_info()

        if self.chat_fn:
            return self.chat_fn(messages, self.config.system_prompt)

        if self.config.tools and self.config.tool_executor:
            return self.ai.chat_with_tools(
                messages=messages,
                system_prompt=self.config.system_prompt,
                tools=self.config.tools,
                tool_executor=self.config.tool_executor,
            )

        # Simple chat (no tools)
        conversation = []
        if self.config.system_prompt:
            conversation.append({"role": "system", "content": self.config.system_prompt})
        conversation.extend(messages)
        response = self.ai.chat(conversation)
        return response.get("content", "I wasn't able to generate a response.")

    def _get_diagnostic_info(self) -> str:
        """Generate diagnostic information."""
        uptime_seconds = int(time.time() - self._start_time) if self._start_time else 0
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        return f"""*{self.config.bot_name} Diagnostics*

:robot_face: *Version:* {self.config.version}
:clock1: *Uptime:* {uptime_str}
:house: *Platform:* Railway
"""

    def start(self, **adapter_kwargs):
        """Start the bot via its adapter.

        Args:
            **adapter_kwargs: Passed to adapter.start() (e.g., register_signals=False).
        """
        self._start_time = time.time()
        logger.info(f"Starting {self.config.bot_name} v{self.config.version}...")
        self.adapter.start(self, **adapter_kwargs)
