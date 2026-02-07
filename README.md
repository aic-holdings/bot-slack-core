# slack-bot-core

Shared Slack bot utilities with dependency-injected AI for AIC Holdings bots.

## Philosophy

**Bots own AI policy. Core owns Slack plumbing.**

- `slack-bot-core` handles: thread history, message formatting, status posting, shutdown, retries
- Your bot handles: AI client setup, system prompt, business logic
- AI is injected via `chat_fn`, not hidden inside core

## Installation

From AIC's private PyPI server:

```bash
pip install slack-bot-core==0.2.0 \
  --extra-index-url https://aic-reader:<password>@pypiserver-production.up.railway.app/simple/
```

Or in `requirements.txt`:
```
--extra-index-url https://aic-reader:<password>@pypiserver-production.up.railway.app/simple/
slack-bot-core==0.2.0
```

Reader credentials in Knox: `pypiserver/reader-username`, `pypiserver/reader-password`

## Quick Start

```python
import os
from slack_bot_core import SlackBotRunner, SlackBotConfig
from artemis_client import ArtemisClient  # Your AI client

# Create your AI client (you own this)
artemis = ArtemisClient(os.environ["ARTEMIS_API_KEY"])

# Configure your bot
config = SlackBotConfig(
    bot_name="My Bot",
    version="1.0.0",
    system_prompt="You are a helpful assistant...",
    status_channel="C08B64J5G7N",  # Optional
)

# Create runner with injected chat function
runner = SlackBotRunner(
    chat_fn=artemis.chat,
    config=config,
)

# Start the bot
runner.start()
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token (xoxb-...) | Yes |
| `SLACK_APP_TOKEN` | Slack App-Level token (xapp-...) | Yes |

## API Reference

### SlackBotConfig

```python
@dataclass
class SlackBotConfig:
    bot_name: str                    # Display name for diagnostics
    version: str                     # Version string
    system_prompt: str               # AI system prompt
    status_channel: Optional[str]    # Channel for startup/shutdown messages
    diagnostic_commands: List[str]   # Commands that trigger diagnostics
                                     # Default: ["status", "info", "diag", ...]
```

### SlackBotRunner

```python
class SlackBotRunner:
    def __init__(
        self,
        chat_fn: Callable[[List[Dict], Optional[str]], str],
        config: SlackBotConfig,
        slack_bot_token: Optional[str] = None,  # Override env var
        slack_app_token: Optional[str] = None,  # Override env var
    ):
        ...

    def start(self):
        """Start the bot (blocking)."""
```

### chat_fn Contract

Your `chat_fn` must match this signature:

```python
def chat_fn(
    messages: List[Dict],      # [{"role": "user"|"assistant", "content": "..."}]
    system_prompt: Optional[str]
) -> str:                      # Response text
```

### Utility Functions

For advanced use cases, utilities are exposed directly:

```python
from slack_bot_core import (
    get_thread_history,         # Fetch Slack thread messages
    build_conversation_messages, # Convert to LLM format
    post_status_message,        # Post to a channel
)

# Example: custom thread handling
messages = get_thread_history(token, channel, thread_ts, limit=50)
conversation = build_conversation_messages(messages)
```

## Features

### Thread-Aware Conversations
Automatically fetches thread history and maintains conversation context.

### Diagnostic Commands
Built-in `/status`, `/ping`, etc. that show uptime and version.

### Graceful Shutdown
Posts status message and handles SIGTERM/SIGINT properly.

### Idempotency
Deduplicates Slack retries to prevent double-processing.

### Pagination & Backoff
Handles rate limits and pagination for thread history.

## Customizing Behavior

### Custom Diagnostic Info

Override `_get_diagnostic_info` or extend `SlackBotConfig`:

```python
config = SlackBotConfig(
    bot_name="My Bot",
    version="1.0.0",
    system_prompt="...",
    diagnostic_commands=["status", "health", "mycommand"],
)
```

### Custom AI Parameters Per-Bot

Since you create the AI client, you control all parameters:

```python
# Bot 1: Fast responses
artemis_fast = ArtemisClient(API_KEY, timeout=30, model="claude-haiku")

# Bot 2: Deep thinking
artemis_deep = ArtemisClient(API_KEY, timeout=120, model="claude-opus")
```

### Custom Message Handling

For complex bots, use utilities directly instead of the runner:

```python
from slack_bolt import App
from slack_bot_core import get_thread_history, build_conversation_messages

app = App(token=SLACK_BOT_TOKEN)

@app.event("app_mention")
def handle(event, say):
    # Your custom logic here
    messages = get_thread_history(...)
    # ... custom processing ...
    say(response)
```

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=slack_bot_core --cov-report=html
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Your Bot                           │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ ArtemisClient   │  │ SlackBotConfig              │  │
│  │ (you own this)  │  │ - bot_name, version         │  │
│  │                 │  │ - system_prompt             │  │
│  │ .chat(msgs, p)  │  │ - status_channel            │  │
│  └────────┬────────┘  └─────────────┬───────────────┘  │
│           │                         │                   │
│           │    chat_fn              │                   │
│           └──────────┬──────────────┘                   │
│                      ▼                                  │
│           ┌──────────────────────┐                      │
│           │   SlackBotRunner     │                      │
│           │   (from core)        │                      │
│           └──────────────────────┘                      │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  slack-bot-core                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ SlackBotRunner                                    │  │
│  │ - Event handling (mentions, DMs)                  │  │
│  │ - Thread history fetching                         │  │
│  │ - Idempotency / dedupe                           │  │
│  │ - Status messages                                 │  │
│  │ - Graceful shutdown                              │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Utilities                                         │  │
│  │ - get_thread_history()                           │  │
│  │ - build_conversation_messages()                  │  │
│  │ - post_status_message()                          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Versioning

We use semantic versioning:
- **Patch** (0.0.x): Bug fixes, no API changes
- **Minor** (0.x.0): New features, backward compatible
- **Major** (x.0.0): Breaking changes

**Always pin versions in production:**
```
slack-bot-core==0.2.0
```

## Contributing

1. Create a feature branch
2. Add tests for new functionality
3. Run `pytest` and `ruff check`
4. Submit PR

## License

MIT
