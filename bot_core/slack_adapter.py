"""
SlackAdapter — Slack interface for bots.

Handles Socket Mode connection, event routing, thread history,
and response posting. Routes messages to BotRunner for processing.
"""

import logging
import os
import re
import signal
import sys
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .utils import build_conversation_messages, get_thread_history, post_status_message

logger = logging.getLogger(__name__)


class SlackAdapter:
    """Slack Socket Mode adapter. Routes messages to a BotRunner."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        app_token: Optional[str] = None,
    ):
        self.bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self.app_token = app_token or os.environ.get("SLACK_APP_TOKEN")

        if not self.bot_token or not self.app_token:
            raise ValueError("Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN")

        self.runner = None

    def start(self, runner):
        """Start Slack Socket Mode, routing messages to runner."""
        self.runner = runner
        self.app = App(token=self.bot_token)
        self._register_handlers()

        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

        self._post_status(
            f":white_check_mark: {runner.config.bot_name} v{runner.config.version} is online!"
        )

        handler = SocketModeHandler(self.app, self.app_token)
        handler.start()

    def _register_handlers(self):
        """Register Slack event handlers."""

        @self.app.event("app_mention")
        def handle_mention(event, say, client):
            self._handle_mention(event, say)

        @self.app.event("message")
        def handle_message(event, say):
            self._handle_dm(event, say)

    def _handle_mention(self, event, say):
        """Handle @mentions of the bot."""
        user_message = event.get("text", "")
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")

        user_message = re.sub(r"<@[A-Z0-9]+>", "", user_message).strip()

        if not user_message:
            say(
                f"Hi! I'm {self.runner.config.bot_name}. Ask me anything!",
                thread_ts=thread_ts,
            )
            return

        try:
            # Build conversation from thread history
            messages = [{"role": "user", "content": user_message}]
            if thread_ts:
                thread_messages = get_thread_history(self.bot_token, channel, thread_ts)
                if thread_messages:
                    messages = build_conversation_messages(thread_messages)

            response = self.runner.handle_message(user_message, messages)
            say(response, thread_ts=thread_ts)

        except Exception as e:
            logger.error(f"Error processing mention: {e}", exc_info=True)
            say(f"Sorry, I encountered an error: {e}", thread_ts=thread_ts)

    def _handle_dm(self, event, say):
        """Handle direct messages."""
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id"):
            return

        user_message = event.get("text", "")

        try:
            messages = [{"role": "user", "content": user_message}]
            response = self.runner.handle_message(user_message, messages)
            say(response)
        except Exception as e:
            logger.error(f"Error processing DM: {e}")
            say(f"Sorry, I encountered an error: {e}")

    def _post_status(self, message: str):
        """Post to status channel if configured."""
        if self.runner and self.runner.config.status_channel:
            post_status_message(
                self.bot_token, self.runner.config.status_channel, message
            )

    def _shutdown_handler(self, signum, frame):
        """Graceful shutdown."""
        logger.info("Shutdown signal received...")
        self._post_status(
            f":warning: {self.runner.config.bot_name} v{self.runner.config.version}"
            " is shutting down..."
        )
        sys.exit(0)
