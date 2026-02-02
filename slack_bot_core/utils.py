"""
Slack utilities - pure functions for thread history, message formatting, status posting.
"""

import re
import logging
from typing import List, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def get_thread_history(
    slack_token: str,
    channel: str,
    thread_ts: str,
    limit: int = 20,
    timeout: float = 10.0,
) -> List[Dict]:
    """
    Fetch thread history from Slack for conversation context.

    Args:
        slack_token: Slack Bot OAuth token
        channel: Channel ID
        thread_ts: Thread timestamp
        limit: Max messages to fetch
        timeout: Request timeout in seconds

    Returns:
        List of Slack message objects
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                "https://slack.com/api/conversations.replies",
                headers={"Authorization": f"Bearer {slack_token}"},
                params={"channel": channel, "ts": thread_ts, "limit": limit}
            )
            data = response.json()
            if data.get("ok"):
                messages = data.get("messages", [])
                logger.debug(f"Got {len(messages)} messages from thread {thread_ts}")
                return messages
            else:
                logger.warning(f"Slack API error: {data.get('error')}")
    except httpx.TimeoutException:
        logger.error("Timeout fetching thread history")
    except Exception as e:
        logger.error(f"Error fetching thread history: {e}")
    return []


def build_conversation_messages(thread_messages: List[Dict]) -> List[Dict]:
    """
    Convert Slack thread messages to LLM conversation format.

    Args:
        thread_messages: Raw Slack messages from conversations.replies

    Returns:
        List of {"role": "user"|"assistant", "content": "..."} dicts
    """
    messages = []
    for msg in thread_messages:
        text = msg.get("text", "")
        # Remove bot mentions from text
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
        if not text:
            continue

        is_bot = msg.get("bot_id") is not None
        role = "assistant" if is_bot else "user"
        messages.append({"role": role, "content": text})

    logger.debug(f"Built conversation with {len(messages)} messages")
    return messages


def post_status_message(
    slack_token: str,
    channel: str,
    message: str,
    timeout: float = 10.0,
) -> bool:
    """
    Post a status message to a Slack channel.

    Args:
        slack_token: Slack Bot OAuth token
        channel: Channel ID to post to
        message: Message text
        timeout: Request timeout in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {slack_token}",
                    "Content-Type": "application/json"
                },
                json={"channel": channel, "text": message}
            )
            data = response.json()
            if not data.get("ok"):
                logger.error(f"Failed to post status: {data.get('error')}")
                return False
            return True
    except Exception as e:
        logger.error(f"Error posting status message: {e}")
        return False
