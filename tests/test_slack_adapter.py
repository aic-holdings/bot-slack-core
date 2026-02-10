"""Tests for bot_core.slack_adapter"""

from unittest.mock import MagicMock, patch

import pytest

from bot_core.slack_adapter import SlackAdapter


class TestSlackAdapterInit:
    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"})
    def test_init_with_env_vars(self):
        adapter = SlackAdapter()
        assert adapter.bot_token == "xoxb-test"
        assert adapter.app_token == "xapp-test"

    def test_init_with_explicit_tokens(self):
        adapter = SlackAdapter(bot_token="xoxb-explicit", app_token="xapp-explicit")
        assert adapter.bot_token == "xoxb-explicit"
        assert adapter.app_token == "xapp-explicit"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_missing_tokens_raises(self):
        with pytest.raises(ValueError, match="Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN"):
            SlackAdapter()


class TestSlackAdapterMention:
    def test_handle_mention_routes_to_runner(self):
        """Mention events are routed to runner.handle_message."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        mock_runner.config.bot_name = "Test Bot"
        mock_runner.handle_message.return_value = "Bot response"
        adapter.runner = mock_runner

        mock_say = MagicMock()
        event = {
            "text": "<@U123BOT> hello there",
            "channel": "C123",
            "ts": "1234567890.123456",
        }

        with patch("bot_core.slack_adapter.get_thread_history", return_value=[]):
            adapter._handle_mention(event, mock_say)

        mock_runner.handle_message.assert_called_once()
        call_args = mock_runner.handle_message.call_args[0]
        assert call_args[0] == "hello there"
        mock_say.assert_called_once_with("Bot response", thread_ts="1234567890.123456")

    def test_handle_mention_empty_text_greets(self):
        """Empty mention text triggers greeting."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        mock_runner.config.bot_name = "Test Bot"
        adapter.runner = mock_runner

        mock_say = MagicMock()
        event = {"text": "<@U123BOT>", "channel": "C123", "ts": "123"}

        adapter._handle_mention(event, mock_say)

        mock_say.assert_called_once()
        assert "Test Bot" in mock_say.call_args[0][0]
        mock_runner.handle_message.assert_not_called()

    def test_handle_mention_with_thread_history(self):
        """Thread history is fetched and passed to runner."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        mock_runner.config.bot_name = "Test Bot"
        mock_runner.handle_message.return_value = "response"
        adapter.runner = mock_runner

        mock_say = MagicMock()
        event = {
            "text": "<@U123BOT> follow up",
            "channel": "C123",
            "thread_ts": "111.222",
            "ts": "111.333",
        }

        thread_msgs = [
            {"text": "original question", "user": "U456"},
            {"text": "bot answer", "bot_id": "B789"},
            {"text": "<@U123BOT> follow up", "user": "U456"},
        ]

        with patch("bot_core.slack_adapter.get_thread_history", return_value=thread_msgs), \
             patch("bot_core.slack_adapter.build_conversation_messages") as mock_build:
            mock_build.return_value = [
                {"role": "user", "content": "original question"},
                {"role": "assistant", "content": "bot answer"},
                {"role": "user", "content": "follow up"},
            ]
            adapter._handle_mention(event, mock_say)

        mock_runner.handle_message.assert_called_once()
        messages = mock_runner.handle_message.call_args[0][1]
        assert len(messages) == 3


class TestSlackAdapterDM:
    def test_handle_dm_routes_to_runner(self):
        """DM events are routed to runner.handle_message."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        mock_runner.handle_message.return_value = "DM response"
        adapter.runner = mock_runner

        mock_say = MagicMock()
        event = {"text": "hello", "channel_type": "im"}

        adapter._handle_dm(event, mock_say)

        mock_runner.handle_message.assert_called_once()
        call_args = mock_runner.handle_message.call_args
        assert call_args[0][0] == "hello"
        assert call_args[0][1] == [{"role": "user", "content": "hello"}]
        assert "log_context" in call_args.kwargs
        assert call_args.kwargs["log_context"]["context"]["event_type"] == "dm"
        mock_say.assert_called_once_with("DM response")

    def test_handle_dm_ignores_non_im(self):
        """Non-IM messages are ignored."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        adapter.runner = mock_runner

        mock_say = MagicMock()
        event = {"text": "hello", "channel_type": "channel"}

        adapter._handle_dm(event, mock_say)

        mock_runner.handle_message.assert_not_called()
        mock_say.assert_not_called()

    def test_handle_dm_ignores_bot_messages(self):
        """Bot messages in DMs are ignored."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        adapter.runner = mock_runner

        mock_say = MagicMock()
        event = {"text": "hello", "channel_type": "im", "bot_id": "B123"}

        adapter._handle_dm(event, mock_say)

        mock_runner.handle_message.assert_not_called()


class TestSlackAdapterStatus:
    def test_post_status_with_channel(self):
        """Posts status when status_channel is configured."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        mock_runner.config.status_channel = "C_STATUS"
        adapter.runner = mock_runner

        with patch("bot_core.slack_adapter.post_status_message") as mock_post:
            adapter._post_status("Test message")

        mock_post.assert_called_once_with("xoxb-test", "C_STATUS", "Test message")

    def test_post_status_without_channel(self):
        """Skips status when no status_channel configured."""
        adapter = SlackAdapter(bot_token="xoxb-test", app_token="xapp-test")
        mock_runner = MagicMock()
        mock_runner.config.status_channel = None
        adapter.runner = mock_runner

        with patch("bot_core.slack_adapter.post_status_message") as mock_post:
            adapter._post_status("Test message")

        mock_post.assert_not_called()
