"""Tests for bot_core.runner"""

from unittest.mock import MagicMock, patch

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
def mock_adapter():
    """Mock adapter that doesn't require Slack tokens."""
    return MagicMock()


@pytest.fixture
def mock_chat_fn():
    """Create a mock chat function."""
    def chat_fn(messages, system_prompt=None):
        return "Mock response"
    return chat_fn


class TestBotConfig:
    """Tests for BotConfig dataclass"""

    def test_required_fields(self):
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert config.bot_name == "Test"
        assert config.version == "1.0.0"
        assert config.system_prompt == "Test prompt"

    def test_optional_status_channel(self):
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert config.status_channel is None

    def test_default_diagnostic_commands(self):
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert "status" in config.diagnostic_commands
        assert "ping" in config.diagnostic_commands
        assert "health" in config.diagnostic_commands

    def test_custom_diagnostic_commands(self):
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
            diagnostic_commands=["status", "custom"],
        )
        assert config.diagnostic_commands == ["status", "custom"]

    def test_default_model(self):
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
        )
        assert config.model == "anthropic/claude-sonnet-4"

    def test_custom_model(self):
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
            model="openai/gpt-4o",
        )
        assert config.model == "openai/gpt-4o"

    def test_tools_and_executor(self):
        tools = [{"type": "function", "function": {"name": "test"}}]
        executor = lambda name, args: {"ok": True}
        config = BotConfig(
            bot_name="Test",
            version="1.0.0",
            system_prompt="Test prompt",
            tools=tools,
            tool_executor=executor,
        )
        assert config.tools == tools
        assert config.tool_executor is executor


class TestBotRunnerInit:
    """Tests for BotRunner initialization"""

    def test_init_with_chat_fn(self, mock_config, mock_chat_fn, mock_adapter):
        """Legacy mode: chat_fn injected, no AI client created."""
        runner = BotRunner(config=mock_config, adapter=mock_adapter, chat_fn=mock_chat_fn)

        assert runner.chat_fn == mock_chat_fn
        assert runner.config == mock_config
        assert runner.ai is None

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-test-key"})
    def test_init_with_built_in_ai(self, mock_config, mock_adapter):
        """New mode: built-in AI client when no chat_fn."""
        runner = BotRunner(config=mock_config, adapter=mock_adapter)

        assert runner.ai is not None
        assert runner.chat_fn is None

    @patch.dict("os.environ", {}, clear=True)
    def test_init_missing_api_key_raises(self, mock_config, mock_adapter):
        """Raises ValueError when OPENROUTER_API_KEY missing and no chat_fn."""
        with pytest.raises(ValueError, match="Missing OPENROUTER_API_KEY"):
            BotRunner(config=mock_config, adapter=mock_adapter)

    @patch.dict(
        "os.environ",
        {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test", "OPENROUTER_API_KEY": "sk-test"},
    )
    def test_default_slack_adapter(self, mock_config):
        """Defaults to SlackAdapter when no adapter provided."""
        from bot_core.slack_adapter import SlackAdapter

        runner = BotRunner(config=mock_config)
        assert isinstance(runner.adapter, SlackAdapter)


class TestBotRunnerDiagnostics:
    """Tests for diagnostic info generation"""

    def test_diagnostic_via_handle_message(self, mock_config, mock_chat_fn, mock_adapter):
        """handle_message returns diagnostic info for diagnostic commands."""
        runner = BotRunner(config=mock_config, adapter=mock_adapter, chat_fn=mock_chat_fn)
        runner._start_time = 1000

        with patch("time.time", return_value=1060):
            result = runner.handle_message("status", [{"role": "user", "content": "status"}])

        assert "1.0.0" in result
        assert "Test Bot" in result
        assert "1m" in result

    def test_diagnostic_info_uptime_formatting(self, mock_config, mock_chat_fn, mock_adapter):
        """Uptime formatted as hours/minutes/seconds."""
        runner = BotRunner(config=mock_config, adapter=mock_adapter, chat_fn=mock_chat_fn)
        runner._start_time = 1000

        with patch("time.time", return_value=1000 + 3661):
            info = runner._get_diagnostic_info()

        assert "1h" in info
        assert "1m" in info


class TestBotRunnerChatFn:
    """Tests for legacy chat_fn mode"""

    def test_chat_fn_called_with_messages_and_prompt(self, mock_config, mock_adapter):
        """chat_fn receives messages and system_prompt via handle_message."""
        received = {}

        def capture_fn(messages, system_prompt=None):
            received["messages"] = messages
            received["system_prompt"] = system_prompt
            return "response"

        runner = BotRunner(config=mock_config, adapter=mock_adapter, chat_fn=capture_fn)
        messages = [{"role": "user", "content": "Hello"}]
        result = runner.handle_message("Hello", messages)

        assert result == "response"
        assert received["messages"] == messages
        assert received["system_prompt"] == "You are a test bot."

    def test_diagnostic_takes_priority_over_chat_fn(self, mock_config, mock_adapter):
        """Diagnostic commands are handled before calling chat_fn."""

        def should_not_be_called(messages, system_prompt=None):
            raise AssertionError("chat_fn should not be called for diagnostic commands")

        runner = BotRunner(config=mock_config, adapter=mock_adapter, chat_fn=should_not_be_called)
        runner._start_time = 1000

        with patch("time.time", return_value=1060):
            result = runner.handle_message("status", [{"role": "user", "content": "status"}])

        assert "Test Bot" in result


class TestBotRunnerBuiltInAI:
    """Tests for built-in AI mode"""

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-test"})
    def test_simple_chat_no_tools(self, mock_config, mock_adapter):
        """Built-in AI simple chat (no tools defined)."""
        runner = BotRunner(config=mock_config, adapter=mock_adapter)
        runner.ai.chat = MagicMock(return_value={"content": "AI says hello"})

        messages = [{"role": "user", "content": "Hello"}]
        result = runner.handle_message("Hello", messages)

        assert result == "AI says hello"
        runner.ai.chat.assert_called_once()
        call_args = runner.ai.chat.call_args[0][0]
        assert call_args[0] == {"role": "system", "content": "You are a test bot."}

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-test"})
    def test_tool_use_mode(self, mock_adapter):
        """Built-in AI with tools delegates to chat_with_tools."""
        executor = MagicMock(return_value={"result": "ok"})
        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        config = BotConfig(
            bot_name="Test Bot",
            version="1.0.0",
            system_prompt="You are a test bot.",
            tools=tools,
            tool_executor=executor,
        )
        runner = BotRunner(config=config, adapter=mock_adapter)
        runner.ai.chat_with_tools = MagicMock(return_value="Tool result")

        messages = [{"role": "user", "content": "Use the tool"}]
        result = runner.handle_message("Use the tool", messages)

        assert result == "Tool result"
        runner.ai.chat_with_tools.assert_called_once_with(
            messages=messages,
            system_prompt="You are a test bot.",
            tools=tools,
            tool_executor=executor,
        )
