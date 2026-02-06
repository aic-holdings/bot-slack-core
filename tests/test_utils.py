"""Tests for slack_bot_core.utils"""

from unittest.mock import MagicMock, patch

from slack_bot_core.utils import (
    build_conversation_messages,
    get_thread_history,
    post_status_message,
)


class TestBuildConversationMessages:
    """Tests for build_conversation_messages()"""

    def test_empty_messages(self):
        """Returns empty list for empty input."""
        result = build_conversation_messages([])
        assert result == []

    def test_user_message(self):
        """Converts user message correctly."""
        messages = [{"text": "Hello bot", "user": "U123"}]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "Hello bot"}]

    def test_bot_message(self):
        """Converts bot message correctly."""
        messages = [{"text": "Hello human", "bot_id": "B123"}]
        result = build_conversation_messages(messages)
        assert result == [{"role": "assistant", "content": "Hello human"}]

    def test_mixed_conversation(self):
        """Handles mixed user/bot conversation."""
        messages = [
            {"text": "Hi", "user": "U123"},
            {"text": "Hello!", "bot_id": "B123"},
            {"text": "How are you?", "user": "U123"},
        ]
        result = build_conversation_messages(messages)
        assert result == [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]

    def test_strips_bot_mentions(self):
        """Removes @mentions from message text."""
        messages = [{"text": "<@U123ABC> hello there", "user": "U456"}]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "hello there"}]

    def test_multiple_mentions(self):
        """Removes multiple @mentions."""
        messages = [{"text": "<@U123> <@U456> hello", "user": "U789"}]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_skips_empty_after_mention_strip(self):
        """Skips messages that become empty after stripping mentions."""
        messages = [
            {"text": "<@U123>", "user": "U456"},
            {"text": "Real message", "user": "U456"},
        ]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "Real message"}]

    def test_skips_empty_text(self):
        """Skips messages with empty text."""
        messages = [
            {"text": "", "user": "U123"},
            {"text": "Hello", "user": "U123"},
        ]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_missing_text_field(self):
        """Handles messages without text field."""
        messages = [
            {"user": "U123"},  # No text
            {"text": "Hello", "user": "U123"},
        ]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_preserves_whitespace_in_content(self):
        """Preserves meaningful whitespace in message content."""
        messages = [{"text": "Line 1\nLine 2", "user": "U123"}]
        result = build_conversation_messages(messages)
        assert result == [{"role": "user", "content": "Line 1\nLine 2"}]


class TestGetThreadHistory:
    """Tests for get_thread_history()"""

    @patch("slack_bot_core.utils.httpx.Client")
    def test_successful_fetch(self, mock_client_class):
        """Successfully fetches thread history."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "Hello", "user": "U123"},
                {"text": "Hi!", "bot_id": "B123"},
            ],
        }

        result = get_thread_history("xoxb-token", "C123", "1234567890.123456")

        assert len(result) == 2
        assert result[0]["text"] == "Hello"
        mock_client.get.assert_called_once()

    @patch("slack_bot_core.utils.httpx.Client")
    def test_api_error(self, mock_client_class):
        """Returns empty list on Slack API error."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }

        result = get_thread_history("xoxb-token", "C123", "1234567890.123456")

        assert result == []

    @patch("slack_bot_core.utils.httpx.Client")
    def test_timeout(self, mock_client_class):
        """Returns empty list on timeout."""
        import httpx

        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        result = get_thread_history("xoxb-token", "C123", "1234567890.123456")

        assert result == []

    @patch("slack_bot_core.utils.httpx.Client")
    def test_custom_limit(self, mock_client_class):
        """Passes custom limit to API."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {"ok": True, "messages": []}

        get_thread_history("xoxb-token", "C123", "1234567890.123456", limit=50)

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 50


class TestPostStatusMessage:
    """Tests for post_status_message()"""

    @patch("slack_bot_core.utils.httpx.Client")
    def test_successful_post(self, mock_client_class):
        """Successfully posts status message."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value.json.return_value = {"ok": True}

        result = post_status_message("xoxb-token", "C123", "Bot is online!")

        assert result is True
        mock_client.post.assert_called_once()

    @patch("slack_bot_core.utils.httpx.Client")
    def test_api_error(self, mock_client_class):
        """Returns False on Slack API error."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }

        result = post_status_message("xoxb-token", "C123", "Bot is online!")

        assert result is False

    @patch("slack_bot_core.utils.httpx.Client")
    def test_network_error(self, mock_client_class):
        """Returns False on network error."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = Exception("Network error")

        result = post_status_message("xoxb-token", "C123", "Bot is online!")

        assert result is False
