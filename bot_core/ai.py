"""
OpenRouter AI client — built into bot-core for all bots.

Handles:
- Chat completions with optional tool-use
- Token usage logging per bot (via X-Title header)
- Tool-use loop (call -> execute -> call -> ... -> text response)
"""

import json
import logging
import time
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

    def chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        log_context: Optional[Dict] = None,
    ) -> Dict:
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

        start = time.time()
        response = self.client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()
        duration_ms = round((time.time() - start) * 1000)

        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        logger.info(
            f"[{self.bot_name}] LLM call: {prompt_tokens}p + {completion_tokens}c",
            extra={
                "model": self.model,
                "tokens_in": prompt_tokens,
                "tokens_out": completion_tokens,
                "duration_ms": duration_ms,
                **(log_context or {}),
            },
        )

        return result["choices"][0]["message"]

    def chat_with_tools(
        self,
        messages: List[Dict],
        system_prompt: Optional[str],
        tools: List[Dict],
        tool_executor: Callable[[str, Dict], Any],
        max_iterations: int = 5,
        log_context: Optional[Dict] = None,
    ) -> str:
        """
        Full tool-use loop. Returns final text response.

        Args:
            messages: Conversation messages [{"role": ..., "content": ...}]
            system_prompt: System prompt to prepend
            tools: OpenRouter tool definitions
            tool_executor: Function (tool_name, tool_args) -> result
            max_iterations: Max tool-use rounds
            log_context: Structured logging context (trace_id, user_id, etc.)
        """
        conversation: List[Dict] = []
        if system_prompt:
            conversation.append({"role": "system", "content": system_prompt})
        conversation.extend(messages)

        for iteration in range(max_iterations):
            try:
                response = self.chat(conversation, tools=tools, log_context=log_context)
            except Exception as e:
                logger.error(f"OpenRouter API error: {e}", extra=log_context or {})
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

                logger.info(f"Tool call [{iteration + 1}]: {name}", extra={
                    "context": {"tool_name": name, "tool_args": args, "iteration": iteration + 1},
                    **(log_context or {}),
                })

                tool_start = time.time()
                try:
                    result = tool_executor(name, args)
                except Exception as e:
                    logger.error(f"Tool execution error in {name}: {e}", extra={
                        "context": {"tool_name": name, "error": str(e)},
                        **(log_context or {}),
                    })
                    result = {"error": f"Failed to execute {name}: {e}"}
                tool_duration_ms = round((time.time() - tool_start) * 1000)

                logger.info(f"Tool result [{iteration + 1}]: {name}", extra={
                    "duration_ms": tool_duration_ms,
                    "context": {
                        "tool_name": name,
                        "tool_result": str(result)[:1000],
                        "success": not isinstance(result, dict) or "error" not in result,
                    },
                    **(log_context or {}),
                })

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, default=str),
                })

        return "I hit the maximum number of steps. Could you simplify your request?"
