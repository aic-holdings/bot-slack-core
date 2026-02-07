"""Tests for bot_core.runner"""

from unittest.mock import patch

import pytest

from bot_core.runner import BotConfig, BotRunner


@pytest.fixture
def mock_config():
    """Create a test config."""
    return BotConfig(
        bot_name="Test Bot",
        version="1.0.0",
        system_prompt="You are a test bot.",
        status_channel="C123TEST",
    )


@pytest.fixture
def mock_chat_fn():
    """Create a mock chat function."""
    def chat_fn(messages, system_prompt=None):
        return "Mock response"
    return chat_fn


class TestBotConfig:
    """Tests for BotConfig dataclass"""

    def test_required_fields(self):
        """Config requires bot_name, version, system_prompt."""
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert config.bot_name == "Test"
        assert config.version == "1.0.0"
        assert config.system_prompt == "Test prompt"

    def test_optional_status_channel(self):
        """status_channel is optional."""
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert config.status_channel is None

    def test_default_diagnostic_commands(self):
        """Default diagnostic commands are set."""
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert "status" in config.diagnostic_commands
        assert "ping" in config.diagnostic_commands
        assert "health" in config.diagnostic_commands

    def test_custom_diagnostic_commands(self):
        """Can override diagnostic commands."""
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
            diagnostic_commands=["status", "custom"],
        )
        assert config.diagnostic_commands == ["status", "custom"]


class TestBotRunnerInit:
    """Tests for BotRunner initialization"""

    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"})
    @patch("bot_core.runner.App")
    def test_init_with_env_vars(self, mock_app_class, mock_config, mock_chat_fn):
        """Initializes with environment variables."""
        runner = BotRunner(chat_fn=mock_chat_fn, config=mock_config)

        assert runner.slack_bot_token == "xoxb-test"
        assert runner.slack_app_token == "xapp-test"
        assert runner.chat_fn == mock_chat_fn
        assert runner.config == mock_config

    @patch("bot_core.runner.App")
    def test_init_with_explicit_tokens(self, mock_app_class, mock_config, mock_chat_fn):
        """Initializes with explicit tokens."""
        runner = BotRunner(
            chat_fn=mock_chat_fn,
            config=mock_config,
            slack_bot_token="xoxb-explicit",
            slack_app_token="xapp-explicit",
        )

        assert runner.slack_bot_token == "xoxb-explicit"
        assert runner.slack_app_token == "xapp-explicit"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_missing_tokens_raises(self, mock_config, mock_chat_fn):
        """Raises ValueError when tokens are missing."""
        with pytest.raises(ValueError, match="Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN"):
            BotRunner(chat_fn=mock_chat_fn, config=mock_config)


class TestBotRunnerDiagnostics:
    """Tests for diagnostic info generation"""

    @patch("bot_core.runner.App")
    def test_diagnostic_info_contains_version(self, mock_app_class, mock_config, mock_chat_fn):
        """Diagnostic info includes bot version."""
        runner = BotRunner(
            chat_fn=mock_chat_fn,
            config=mock_config,
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
        )
        runner._start_time = 1000

        with patch("time.time", return_value=1060):  # 60 seconds uptime
            info = runner._get_diagnostic_info()

        assert "1.0.0" in info
        assert "Test Bot" in info
        assert "1m" in info  # 60 seconds = 1 minute

    @patch("bot_core.runner.App")
    def test_diagnostic_info_uptime_formatting(self, mock_app_class, mock_config, mock_chat_fn):
        """Diagnostic info formats uptime correctly."""
        runner = BotRunner(
            chat_fn=mock_chat_fn,
            config=mock_config,
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
        )
        runner._start_time = 1000

        # Test hours, minutes, seconds
        with patch("time.time", return_value=1000 + 3661):  # 1h 1m 1s
            info = runner._get_diagnostic_info()

        assert "1h" in info
        assert "1m" in info


class TestBotRunnerChatFnContract:
    """Tests for chat_fn contract validation"""

    @patch("bot_core.runner.App")
    def test_chat_fn_receives_messages_list(self, mock_app_class, mock_config):
        """chat_fn receives messages as list of dicts."""
        received_messages = []

        def capture_chat_fn(messages, system_prompt=None):
            received_messages.append(messages)
            return "response"

        runner = BotRunner(
            chat_fn=capture_chat_fn,
            config=mock_config,
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
        )

        # Simulate processing a message
        test_messages = [{"role": "user", "content": "Hello"}]
        runner.chat_fn(test_messages, "system prompt")

        assert received_messages[0] == test_messages

    @patch("bot_core.runner.App")
    def test_chat_fn_receives_system_prompt(self, mock_app_class, mock_config):
        """chat_fn receives system prompt."""
        received_prompts = []

        def capture_chat_fn(messages, system_prompt=None):
            received_prompts.append(system_prompt)
            return "response"

        runner = BotRunner(
            chat_fn=capture_chat_fn,
            config=mock_config,
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
        )

        runner.chat_fn([], "My system prompt")

        assert received_prompts[0] == "My system prompt"
