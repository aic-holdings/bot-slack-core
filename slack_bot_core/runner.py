"""
SlackBotRunner - Orchestrates Slack events with injected AI chat function.
"""

import os
import signal
import sys
import time
import logging
from typing import Callable, List, Dict, Optional
from dataclasses import dataclass, field

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .utils import get_thread_history, build_conversation_messages, post_status_message

logger = logging.getLogger(__name__)


@dataclass
class SlackBotConfig:
    """Configuration for a Slack bot."""
    bot_name: str
    version: str
    system_prompt: str
    status_channel: Optional[str] = None
    diagnostic_commands: List[str] = field(
        default_factory=lambda: ["status", "info", "diag", "diagnostics", "version", "health", "ping"]
    )


class SlackBotRunner:
    """
    Orchestrates Slack bot events with dependency-injected AI.

    The bot owns:
    - Slack token management
    - Event handling (mentions, DMs)
    - Thread history fetching
    - Status messages

    You provide:
    - chat_fn: Function that takes (messages, system_prompt) -> response string
    - config: Bot name, version, system prompt, etc.
    """

    def __init__(
        self,
        chat_fn: Callable[[List[Dict], Optional[str]], str],
        config: SlackBotConfig,
        slack_bot_token: Optional[str] = None,
        slack_app_token: Optional[str] = None,
    ):
        """
        Initialize the bot runner.

        Args:
            chat_fn: AI chat function (messages, system_prompt) -> response
            config: Bot configuration
            slack_bot_token: Override SLACK_BOT_TOKEN env var
            slack_app_token: Override SLACK_APP_TOKEN env var
        """
        self.chat_fn = chat_fn
        self.config = config

        self.slack_bot_token = slack_bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self.slack_app_token = slack_app_token or os.environ.get("SLACK_APP_TOKEN")

        if not self.slack_bot_token or not self.slack_app_token:
            raise ValueError("Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN")

        self._start_time = 0.0
        self._bot_user_id: Optional[str] = None

        # Initialize Slack app
        self.app = App(token=self.slack_bot_token)
        self._register_handlers()

    def _register_handlers(self):
        """Register Slack event handlers."""

        @self.app.event("app_mention")
        def handle_mention(event, say, client):
            self._handle_mention(event, say, client)

        @self.app.event("message")
        def handle_message(event, say):
            self._handle_dm(event, say)

    def _handle_mention(self, event, say, client):
        """Handle @mentions of the bot."""
        import re

        user_message = event.get("text", "")
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")

        # Remove bot mention from message
        user_message = re.sub(r"<@[A-Z0-9]+>", "", user_message).strip()

        if not user_message:
            say(f"Hi! I'm {self.config.bot_name}. Ask me anything!", thread_ts=thread_ts)
            return

        # Check for diagnostic commands
        if user_message.lower() in self.config.diagnostic_commands:
            say(self._get_diagnostic_info(), thread_ts=thread_ts)
            return

        try:
            # Cache bot user ID on first use
            if self._bot_user_id is None:
                auth_info = client.auth_test()
                self._bot_user_id = auth_info.get("user_id", "")

            # Get thread history for conversation context
            conversation_history = None
            if thread_ts:
                thread_messages = get_thread_history(
                    self.slack_bot_token, channel, thread_ts
                )
                if thread_messages:
                    conversation_history = build_conversation_messages(thread_messages)

            # Call injected chat function
            if conversation_history:
                response = self.chat_fn(conversation_history, self.config.system_prompt)
            else:
                messages = [{"role": "user", "content": user_message}]
                response = self.chat_fn(messages, self.config.system_prompt)

            say(response, thread_ts=thread_ts)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            say(f"Sorry, I encountered an error: {str(e)}", thread_ts=thread_ts)

    def _handle_dm(self, event, say):
        """Handle direct messages."""
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id"):
            return

        user_message = event.get("text", "")

        try:
            messages = [{"role": "user", "content": user_message}]
            response = self.chat_fn(messages, self.config.system_prompt)
            say(response)
        except Exception as e:
            logger.error(f"Error processing DM: {e}")
            say(f"Sorry, I encountered an error: {str(e)}")

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

    def _post_status(self, message: str):
        """Post to status channel if configured."""
        if self.config.status_channel:
            post_status_message(
                self.slack_bot_token,
                self.config.status_channel,
                message
            )

    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received...")
        self._post_status(
            f":warning: {self.config.bot_name} v{self.config.version} is shutting down..."
        )
        sys.exit(0)

    def start(self):
        """Start the bot."""
        # Register shutdown handlers
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

        # Track startup time
        self._start_time = time.time()

        logger.info(f"Starting {self.config.bot_name} v{self.config.version}...")
        self._post_status(
            f":white_check_mark: {self.config.bot_name} v{self.config.version} is online!"
        )

        handler = SocketModeHandler(self.app, self.slack_app_token)
        handler.start()
