# Bot Core Library

Before making changes, read the `.taskr/` folder:
- `.taskr/service.yaml` — service identity, owner, deploy target
- `.taskr/govern.yaml` — constraints, boundaries, required approvals
- `.taskr/ship.yaml` — branching strategy, CI/CD, release config

## Key Rules
- NEVER break the `chat_fn` contract: `(messages, system_prompt) -> str`
- NEVER add hard AI dependencies — AI is injected, not owned by core
- Backward-compatible changes only — all bots depend on this library
- Semantic versioning strictly enforced (breaking = major bump)
- This is a pip-installable library, not a deployed service

## Architecture
- `bot_core/runner.py` — BotRunner + BotConfig
- `bot_core/utils.py` — thread history, conversation building, status messages
- `bot_core/scanner.py` — channel scanning, bot conversation extraction
- `docs/` — shared patterns (preview-bot-pattern.md)

## Consumers
All AIC bots depend on this: meridian-bot, sable-bot, ciso-bot. BotBot (in taskr) uses the scanner.
