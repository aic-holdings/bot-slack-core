"""
OpenRouter AI client — built into bot-core for all bots.

Handles:
- Chat completions with optional tool-use
- Token usage logging per bot (via X-Title header)
- Tool-use loop (call -> execute -> call -> ... -> text response)
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4"


class OpenRouterClient:
    """OpenRouter API client with tool-use support and per-bot attribution."""

    def __init__(self, api_key: str, bot_name: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.bot_name = bot_name
        self.model = model
        self.client = httpx.Client(timeout=60.0)

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        """Single chat completion. Returns the message dict from the response."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": f"https://{self.bot_name.lower().replace(' ', '-')}.railway.app",
            "X-Title": self.bot_name,
        }

        payload: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools

        response = self.client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        usage = result.get("usage", {})
        if usage:
            prompt = usage.get("prompt_tokens", 0)
            completion = usage.get("completion_tokens", 0)
            total = usage.get("total_tokens", 0)
            logger.info(f"[{self.bot_name}] tokens: {prompt}p + {completion}c = {total}t")

        return result["choices"][0]["message"]

    def chat_with_tools(
        self,
        messages: List[Dict],
        system_prompt: Optional[str],
        tools: List[Dict],
        tool_executor: Callable[[str, Dict], Any],
        max_iterations: int = 5,
    ) -> str:
        """
        Full tool-use loop. Returns final text response.

        Args:
            messages: Conversation messages [{"role": ..., "content": ...}]
            system_prompt: System prompt to prepend
            tools: OpenRouter tool definitions
            tool_executor: Function (tool_name, tool_args) -> result
            max_iterations: Max tool-use rounds
        """
        conversation: List[Dict] = []
        if system_prompt:
            conversation.append({"role": "system", "content": system_prompt})
        conversation.extend(messages)

        for iteration in range(max_iterations):
            try:
                response = self.chat(conversation, tools=tools)
            except Exception as e:
                logger.error(f"OpenRouter API error: {e}")
                return f"Error communicating with AI: {e}"

            tool_calls = response.get("tool_calls")

            if not tool_calls:
                return response.get("content", "I wasn't able to generate a response.")

            conversation.append(response)

            for tool_call in tool_calls:
                fn = tool_call["function"]
                name = fn["name"]
                raw_args = fn.get("arguments", "")
                if not raw_args:
                    args = {}
                elif isinstance(raw_args, str):
                    args = json.loads(raw_args)
                else:
                    args = raw_args

                logger.info(f"Tool call [{iteration + 1}]: {name}({args})")

                try:
                    result = tool_executor(name, args)
                except Exception as e:
                    logger.error(f"Tool execution error in {name}: {e}")
                    result = {"error": f"Failed to execute {name}: {e}"}

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, default=str),
                })

        return "I hit the maximum number of steps. Could you simplify your request?"
