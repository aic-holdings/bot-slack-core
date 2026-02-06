# Slack Bot Core Library

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
- `slack_bot_core/runner.py` — SlackBotRunner + SlackBotConfig
- `slack_bot_core/utils.py` — thread history, conversation building, status messages
- `docs/` — shared patterns (preview-bot-pattern.md)

## Consumers
All AIC Slack bots depend on this: aic-slack-bot (Meridian), bot-ciso, bot-sable, bot-taskr.
