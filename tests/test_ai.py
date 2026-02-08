"""Tests for bot_core.ai"""

from unittest.mock import MagicMock

import pytest

from bot_core.ai import OpenRouterClient


@pytest.fixture
def client():
    """Create a client with mocked httpx."""
    c = OpenRouterClient(api_key="sk-test", bot_name="Test Bot")
    c.client = MagicMock()
    return c


def _mock_response(data):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


class TestOpenRouterClientInit:
    def test_defaults(self):
        c = OpenRouterClient(api_key="sk-test", bot_name="Wrike Bot")
        assert c.bot_name == "Wrike Bot"
        assert c.model == "anthropic/claude-sonnet-4"

    def test_custom_model(self):
        c = OpenRouterClient(api_key="sk-test", bot_name="Test", model="openai/gpt-4o")
        assert c.model == "openai/gpt-4o"


class TestOpenRouterChat:
    def test_chat_returns_message(self, client):
        """chat() returns the message dict from the response."""
        client.client.post.return_value = _mock_response({
            "choices": [{"message": {"content": "Hello back"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

        result = client.chat([{"role": "user", "content": "Hello"}])

        assert result == {"content": "Hello back"}

    def test_chat_sends_correct_headers(self, client):
        """chat() sends Authorization, X-Title, HTTP-Referer headers."""
        client.client.post.return_value = _mock_response({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        })

        client.chat([{"role": "user", "content": "test"}])

        call_kwargs = client.client.post.call_args
        headers = call_kwargs.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["X-Title"] == "Test Bot"
        assert "test-bot" in headers["HTTP-Referer"]

    def test_chat_sends_tools_when_provided(self, client):
        """chat() includes tools in payload when provided."""
        client.client.post.return_value = _mock_response({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        })

        tools = [{"type": "function", "function": {"name": "search"}}]
        client.chat([{"role": "user", "content": "test"}], tools=tools)

        payload = client.client.post.call_args.kwargs["json"]
        assert payload["tools"] == tools

    def test_chat_omits_tools_when_none(self, client):
        """chat() does not include tools key when tools is None."""
        client.client.post.return_value = _mock_response({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        })

        client.chat([{"role": "user", "content": "test"}])

        payload = client.client.post.call_args.kwargs["json"]
        assert "tools" not in payload


class TestOpenRouterChatWithTools:
    def test_tool_use_loop(self, client):
        """Full loop: call -> tool_calls -> execute -> call -> text."""
        tool_call_response = _mock_response({
            "choices": [{"message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "get_folders", "arguments": "{}"},
                }],
            }}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })
        text_response = _mock_response({
            "choices": [{"message": {"content": "Here are your folders."}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        })
        client.client.post.side_effect = [tool_call_response, text_response]

        executor = MagicMock(return_value=[{"name": "Engineering"}])
        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "Show folders"}],
            system_prompt="You are a test bot.",
            tools=[{"type": "function", "function": {"name": "get_folders"}}],
            tool_executor=executor,
        )

        assert result == "Here are your folders."
        executor.assert_called_once_with("get_folders", {})

    def test_system_prompt_prepended(self, client):
        """System prompt is prepended to conversation."""
        client.client.post.return_value = _mock_response({
            "choices": [{"message": {"content": "response"}}],
            "usage": {},
        })

        client.chat_with_tools(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful.",
            tools=[],
            tool_executor=MagicMock(),
        )

        payload = client.client.post.call_args.kwargs["json"]
        assert payload["messages"][0] == {"role": "system", "content": "Be helpful."}

    def test_max_iterations_stops_loop(self, client):
        """Stops after max_iterations if AI keeps calling tools."""
        tool_call_response = _mock_response({
            "choices": [{"message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "search", "arguments": '{"q": "test"}'},
                }],
            }}],
            "usage": {},
        })
        client.client.post.return_value = tool_call_response

        executor = MagicMock(return_value={"results": []})
        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "Search"}],
            system_prompt=None,
            tools=[{"type": "function", "function": {"name": "search"}}],
            tool_executor=executor,
            max_iterations=2,
        )

        assert "maximum number of steps" in result
        assert executor.call_count == 2

    def test_tool_executor_error_handled(self, client):
        """Tool executor exceptions are caught and returned as error results."""
        tool_call_response = _mock_response({
            "choices": [{"message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "bad_tool", "arguments": "{}"},
                }],
            }}],
            "usage": {},
        })
        text_response = _mock_response({
            "choices": [{"message": {"content": "Sorry, that failed."}}],
            "usage": {},
        })
        client.client.post.side_effect = [tool_call_response, text_response]

        executor = MagicMock(side_effect=RuntimeError("Connection refused"))
        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "Try it"}],
            system_prompt=None,
            tools=[{"type": "function", "function": {"name": "bad_tool"}}],
            tool_executor=executor,
        )

        assert result == "Sorry, that failed."

    def test_api_error_returns_message(self, client):
        """OpenRouter API errors are returned as readable messages."""
        client.client.post.side_effect = Exception("503 Service Unavailable")

        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt=None,
            tools=[],
            tool_executor=MagicMock(),
        )

        assert "Error communicating with AI" in result
