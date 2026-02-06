"""
Channel scanning utilities for bot conversation discovery and extraction.

Provides functions to discover channels a bot participates in,
fetch channel history with pagination, and extract full bot conversation threads.
"""

import logging
from typing import List, Dict, Optional

import httpx

from .utils import get_thread_history

logger = logging.getLogger(__name__)


def get_channel_history(
    slack_token: str,
    channel: str,
    oldest: Optional[str] = None,
    limit: int = 100,
    timeout: float = 10.0,
) -> List[Dict]:
    """
    Fetch channel message history from Slack with cursor pagination.

    Args:
        slack_token: Slack Bot OAuth token
        channel: Channel ID
        oldest: Only messages after this Unix timestamp
        limit: Max messages to fetch across all pages
        timeout: Request timeout in seconds

    Returns:
        List of Slack message objects
    """
    messages = []
    cursor = None

    try:
        with httpx.Client(timeout=timeout) as client:
            while len(messages) < limit:
                params = {
                    "channel": channel,
                    "limit": min(200, limit - len(messages)),
                }
                if oldest:
                    params["oldest"] = oldest
                if cursor:
                    params["cursor"] = cursor

                response = client.get(
                    "https://slack.com/api/conversations.history",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    params=params,
                )
                data = response.json()

                if not data.get("ok"):
                    logger.warning(f"Slack API error in conversations.history: {data.get('error')}")
                    return messages

                messages.extend(data.get("messages", []))

                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

    except httpx.TimeoutException:
        logger.error("Timeout fetching channel history")
    except Exception as e:
        logger.error(f"Error fetching channel history: {e}")

    logger.debug(f"Got {len(messages)} messages from channel {channel}")
    return messages


def get_channels_for_bot(
    slack_token: str,
    timeout: float = 10.0,
) -> List[Dict]:
    """
    Discover all channels the bot is a member of.

    Args:
        slack_token: Slack Bot OAuth token
        timeout: Request timeout in seconds

    Returns:
        List of Slack channel objects
    """
    channels = []
    cursor = None

    try:
        with httpx.Client(timeout=timeout) as client:
            while True:
                params = {
                    "types": "public_channel,private_channel",
                    "limit": 200,
                }
                if cursor:
                    params["cursor"] = cursor

                response = client.get(
                    "https://slack.com/api/conversations.list",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    params=params,
                )
                data = response.json()

                if not data.get("ok"):
                    logger.warning(f"Slack API error in conversations.list: {data.get('error')}")
                    return channels

                channels.extend(data.get("channels", []))

                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

    except httpx.TimeoutException:
        logger.error("Timeout fetching channel list")
    except Exception as e:
        logger.error(f"Error fetching channel list: {e}")

    logger.debug(f"Discovered {len(channels)} channels")
    return channels


def get_bot_conversations(
    slack_token: str,
    channel: str,
    bot_user_id: str,
    oldest: Optional[str] = None,
    limit: int = 50,
    timeout: float = 10.0,
) -> List[Dict]:
    """
    Extract full conversation threads where the bot participated.

    Identifies threads where the bot sent a message (by user_id or bot_id)
    or was @mentioned, then fetches the complete thread for each.

    Args:
        slack_token: Slack Bot OAuth token
        channel: Channel ID to scan
        bot_user_id: The bot's U-prefixed Slack user ID
        oldest: Only messages after this Unix timestamp
        limit: Max threads to return (cost budget)
        timeout: Request timeout in seconds

    Returns:
        List of conversation dicts with keys:
            channel, thread_ts, permalink, messages, bot_user_id
    """
    messages = get_channel_history(slack_token, channel, oldest=oldest, timeout=timeout)

    # Find threads where bot participated
    seen_threads = set()
    bot_thread_timestamps = []

    for msg in messages:
        thread_ts = msg.get("thread_ts", msg.get("ts"))
        if not thread_ts or thread_ts in seen_threads:
            continue

        is_bot_sender = (
            msg.get("user") == bot_user_id
            or msg.get("bot_id") is not None
        )
        is_bot_mentioned = f"<@{bot_user_id}>" in msg.get("text", "")

        if is_bot_sender or is_bot_mentioned:
            seen_threads.add(thread_ts)
            bot_thread_timestamps.append(thread_ts)

        if len(bot_thread_timestamps) >= limit:
            break

    # Fetch full thread for each
    conversations = []
    for thread_ts in bot_thread_timestamps:
        thread_messages = get_thread_history(
            slack_token, channel, thread_ts, timeout=timeout
        )
        if not thread_messages:
            continue

        # Build permalink: https://slack.com/archives/{channel}/p{ts_without_dot}
        permalink_ts = thread_ts.replace(".", "")
        permalink = f"https://slack.com/archives/{channel}/p{permalink_ts}"

        conversations.append({
            "channel": channel,
            "thread_ts": thread_ts,
            "permalink": permalink,
            "messages": thread_messages,
            "bot_user_id": bot_user_id,
        })

    logger.debug(
        f"Found {len(conversations)} bot conversations in channel {channel}"
    )
    return conversations
