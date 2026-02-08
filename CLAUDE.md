# Bot Core Library

Before making changes, read the `.taskr/` folder:
- `.taskr/service.yaml` — service identity, owner, deploy target
- `.taskr/govern.yaml` — constraints, boundaries, required approvals
- `.taskr/ship.yaml` — branching strategy, CI/CD, release config

## Architecture (v0.4.0)

**AI is the core, human interface is the adapter.**

- `bot_core/ai.py` — OpenRouterClient (built-in AI with tool-use, token logging, X-Title)
- `bot_core/runner.py` — BotRunner + BotConfig (orchestrates AI + adapter)
- `bot_core/slack_adapter.py` — SlackAdapter (Slack Socket Mode, event routing)
- `bot_core/utils.py` — thread history, conversation building, status messages
- `bot_core/scanner.py` — channel scanning, bot conversation extraction

## Key Rules
- AI is BUILT IN — bots do NOT implement their own AI clients
- Slack is an ADAPTER — swappable, not hardcoded
- Legacy `chat_fn` still supported for migration (sable-bot, meridian-bot)
- One OPENROUTER_API_KEY shared across all bots (Railway shared variable)
- Per-bot attribution via OpenRouter X-Title header (from bot_name)
- This is a pip-installable library, not a deployed service

## Bot Pattern (new)
```python
config = BotConfig(
    bot_name="My Bot",
    version="1.0.0",
    system_prompt="You are...",
    tools=TOOLS,              # optional
    tool_executor=exec_tool,  # optional
)
BotRunner(config=config).start()
```

## Consumers
All AIC bots depend on this: wrike-bot, meridian-bot, sable-bot, ciso-bot.
