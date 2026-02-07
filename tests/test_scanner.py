"""Tests for bot_core.scanner"""

from unittest.mock import MagicMock, patch

from bot_core.scanner import (
    get_bot_conversations,
    get_channel_history,
    get_channels_for_bot,
)


class TestGetChannelHistory:
    """Tests for get_channel_history()"""

    @patch("bot_core.scanner.httpx.Client")
    def test_successful_fetch(self, mock_client_class):
        """Successfully fetches channel history."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "Hello", "user": "U123", "ts": "1234567890.000001"},
                {"text": "Hi!", "bot_id": "B123", "ts": "1234567890.000002"},
            ],
        }

        result = get_channel_history("xoxb-token", "C123")

        assert len(result) == 2
        assert result[0]["text"] == "Hello"
        mock_client.get.assert_called_once()

    @patch("bot_core.scanner.httpx.Client")
    def test_api_error_returns_empty(self, mock_client_class):
        """Returns empty list on Slack API error."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }

        result = get_channel_history("xoxb-token", "C123")

        assert result == []

    @patch("bot_core.scanner.httpx.Client")
    def test_timeout_returns_empty(self, mock_client_class):
        """Returns empty list on timeout."""
        import httpx

        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        result = get_channel_history("xoxb-token", "C123")

        assert result == []

    @patch("bot_core.scanner.httpx.Client")
    def test_pagination_two_pages(self, mock_client_class):
        """Handles cursor pagination across two pages."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.side_effect = [
            {
                "ok": True,
                "messages": [{"text": "Page 1", "ts": "1.0"}],
                "response_metadata": {"next_cursor": "cursor_abc"},
            },
            {
                "ok": True,
                "messages": [{"text": "Page 2", "ts": "2.0"}],
            },
        ]

        result = get_channel_history("xoxb-token", "C123", limit=200)

        assert len(result) == 2
        assert result[0]["text"] == "Page 1"
        assert result[1]["text"] == "Page 2"
        assert mock_client.get.call_count == 2

    @patch("bot_core.scanner.httpx.Client")
    def test_oldest_param_passed(self, mock_client_class):
        """Passes oldest parameter to API."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {"ok": True, "messages": []}

        get_channel_history("xoxb-token", "C123", oldest="1700000000.000000")

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["oldest"] == "1700000000.000000"


class TestGetChannelsForBot:
    """Tests for get_channels_for_bot()"""

    @patch("bot_core.scanner.httpx.Client")
    def test_returns_channels(self, mock_client_class):
        """Returns list of channel objects."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "ok": True,
            "channels": [
                {"id": "C001", "name": "general"},
                {"id": "C002", "name": "trading"},
            ],
        }

        result = get_channels_for_bot("xoxb-token")

        assert len(result) == 2
        assert result[0]["id"] == "C001"

    @patch("bot_core.scanner.httpx.Client")
    def test_api_error_returns_empty(self, mock_client_class):
        """Returns empty list on API error."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "ok": False,
            "error": "missing_scope",
        }

        result = get_channels_for_bot("xoxb-token")

        assert result == []

    @patch("bot_core.scanner.httpx.Client")
    def test_pagination(self, mock_client_class):
        """Handles cursor pagination."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value.json.side_effect = [
            {
                "ok": True,
                "channels": [{"id": "C001", "name": "general"}],
                "response_metadata": {"next_cursor": "cursor_abc"},
            },
            {
                "ok": True,
                "channels": [{"id": "C002", "name": "trading"}],
            },
        ]

        result = get_channels_for_bot("xoxb-token")

        assert len(result) == 2
        assert mock_client.get.call_count == 2


class TestGetBotConversations:
    """Tests for get_bot_conversations()"""

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_finds_bot_threads(self, mock_history, mock_thread):
        """Identifies and fetches threads where bot participated."""
        mock_history.return_value = [
            {"text": "Hello bot", "user": "U999", "ts": "1.0", "thread_ts": "1.0"},
            {"text": "I can help!", "user": "UBOT123", "ts": "1.1", "thread_ts": "1.0"},
        ]
        mock_thread.return_value = [
            {"text": "Hello bot", "user": "U999", "ts": "1.0"},
            {"text": "I can help!", "user": "UBOT123", "ts": "1.1"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert len(result) == 1
        assert result[0]["thread_ts"] == "1.0"
        assert result[0]["channel"] == "C123"
        assert len(result[0]["messages"]) == 2

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_respects_limit(self, mock_history, mock_thread):
        """Respects the limit parameter for thread count."""
        mock_history.return_value = [
            {"text": "Thread 1", "user": "UBOT123", "ts": "1.0"},
            {"text": "Thread 2", "user": "UBOT123", "ts": "2.0"},
            {"text": "Thread 3", "user": "UBOT123", "ts": "3.0"},
        ]
        mock_thread.return_value = [{"text": "reply", "ts": "1.0"}]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123", limit=2)

        assert len(result) == 2

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_deduplicates_threads(self, mock_history, mock_thread):
        """Deduplicates threads with same thread_ts."""
        mock_history.return_value = [
            {"text": "msg 1", "user": "UBOT123", "ts": "1.1", "thread_ts": "1.0"},
            {"text": "msg 2", "user": "UBOT123", "ts": "1.2", "thread_ts": "1.0"},
        ]
        mock_thread.return_value = [
            {"text": "msg 1", "user": "UBOT123", "ts": "1.1"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert len(result) == 1

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_bot_as_sender(self, mock_history, mock_thread):
        """Detects bot as direct sender by user_id."""
        mock_history.return_value = [
            {"text": "I responded", "user": "UBOT123", "ts": "1.0"},
        ]
        mock_thread.return_value = [
            {"text": "I responded", "user": "UBOT123", "ts": "1.0"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert len(result) == 1

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_bot_mentioned(self, mock_history, mock_thread):
        """Detects bot via @mention in message text."""
        mock_history.return_value = [
            {"text": "<@UBOT123> help me", "user": "U999", "ts": "1.0"},
        ]
        mock_thread.return_value = [
            {"text": "<@UBOT123> help me", "user": "U999", "ts": "1.0"},
            {"text": "Sure!", "user": "UBOT123", "ts": "1.1"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert len(result) == 1

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_permalink_format(self, mock_history, mock_thread):
        """Builds correct Slack permalink from channel and ts."""
        mock_history.return_value = [
            {"text": "Hello", "user": "UBOT123", "ts": "1234567890.123456"},
        ]
        mock_thread.return_value = [
            {"text": "Hello", "user": "UBOT123", "ts": "1234567890.123456"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert result[0]["permalink"] == "https://slack.com/archives/C123/p1234567890123456"

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_empty_channel(self, mock_history, mock_thread):
        """Returns empty list for channel with no bot messages."""
        mock_history.return_value = [
            {"text": "Just humans here", "user": "U999", "ts": "1.0"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert result == []
        mock_thread.assert_not_called()

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_bot_id_detection(self, mock_history, mock_thread):
        """Detects bot messages via bot_id field."""
        mock_history.return_value = [
            {"text": "Bot reply", "bot_id": "B123", "ts": "1.0"},
        ]
        mock_thread.return_value = [
            {"text": "Bot reply", "bot_id": "B123", "ts": "1.0"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert len(result) == 1

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_skips_empty_threads(self, mock_history, mock_thread):
        """Skips threads where get_thread_history returns empty."""
        mock_history.return_value = [
            {"text": "Hello", "user": "UBOT123", "ts": "1.0"},
        ]
        mock_thread.return_value = []

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert result == []

    @patch("bot_core.scanner.get_thread_history")
    @patch("bot_core.scanner.get_channel_history")
    def test_bot_user_id_in_result(self, mock_history, mock_thread):
        """Each conversation dict includes the bot_user_id."""
        mock_history.return_value = [
            {"text": "Hello", "user": "UBOT123", "ts": "1.0"},
        ]
        mock_thread.return_value = [
            {"text": "Hello", "user": "UBOT123", "ts": "1.0"},
        ]

        result = get_bot_conversations("xoxb-token", "C123", "UBOT123")

        assert result[0]["bot_user_id"] == "UBOT123"
