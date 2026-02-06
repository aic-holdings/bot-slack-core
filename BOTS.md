# AIC Slack Bot Ecosystem

## Naming Convention

All Slack bot repos follow **`slack-bot-{name}`**:

| Repo | Bot Name | What It Does |
|------|----------|---|
| [slack-bot-core](https://github.com/aic-holdings/slack-bot-core) | — | Shared library (not a bot). Slack plumbing, thread history, ChannelScanner. |
| [slack-bot-meridian](https://github.com/aic-holdings/slack-bot-meridian) | Meridian | Trading idea journal. Market data, portfolio analysis, research tools. |
| [slack-bot-taskr](https://github.com/aic-holdings/slack-bot-taskr) | Taskr Bot | Task management interface. Also serves as quality reviewer for all bots. |
| [slack-bot-sable](https://github.com/aic-holdings/slack-bot-sable) | Sable | Portfolio data queries and risk analysis. |
| [slack-bot-ciso](https://github.com/aic-holdings/slack-bot-ciso) | CISO | Sentinel AI CISO — security posture and compliance. |

## Architecture

```
slack-bot-core (shared library, v0.2.0)
├── SlackBotRunner    — Socket Mode event handler
├── SlackBotConfig    — configuration dataclass
├── ChannelScanner    — thread history for BotBot reviews
└── utils             — thread history, message formatting, status posts

Each bot:
├── Imports slack-bot-core for Slack plumbing
├── Owns its AI client (injected via chat_fn, not in core)
├── Owns its business logic and tools
└── Declares review profile in .taskr/bot.yaml
```

Core principle: **Bots own AI policy. Core owns Slack plumbing.**

## Railway

All bots deploy to a single Railway project: **`slack-bots`**

Each bot is a service inside that project:
- `meridian-bot` — slack-bot-meridian
- `taskr-bot` — slack-bot-taskr
- `sable-bot` — slack-bot-sable (if deployed)
- `ciso-bot` — slack-bot-ciso (if deployed)

## Knox Secrets

Bot credentials live in Knox under `slack-bots/{bot-name}/`:

```
slack-bots/meridian/bot-token    — Meridian's SLACK_BOT_TOKEN
slack-bots/taskr/bot-token       — Taskr Bot's SLACK_BOT_TOKEN
slack-bots/sable/bot-token       — Sable's SLACK_BOT_TOKEN
slack-bots/ciso/bot-token        — CISO's SLACK_BOT_TOKEN
```

Bots reference credentials in `.taskr/bot.yaml`:
```yaml
review:
  credential: knox://slack-bots/meridian/bot-token
```

BotBot resolves these at runtime via `resolve_credential()` in `botbot/config.py`.

## BotBot (Quality Reviews)

BotBot is **not a Slack bot** — it's a backend review engine that lives in the [taskr](https://github.com/aic-holdings/taskr) monorepo at `botbot/`.

Pipeline:
1. Reads bot conversations via ChannelScanner (using the bot's own Slack token from Knox)
2. Analyzes with second-opinion AI via Artemis
3. Writes findings as taskr devlogs
4. Taskr Bot surfaces findings to humans

Each bot opts in by adding a review section to `.taskr/bot.yaml`:

```yaml
review:
  enabled: true
  frequency: daily
  credential: knox://slack-bots/{name}/bot-token
  scan_channels: all
  focus:
    - accuracy of responses
    - tool call failures
    - user satisfaction signals
  ignore:
    - diagnostic commands
    - status messages
```

## Adding a New Bot

1. Create repo: `aic-holdings/slack-bot-{name}`
2. Add `slack-bot-core` as dependency:
   ```
   slack-bot-core @ git+https://github.com/aic-holdings/slack-bot-core.git@v0.2.0
   ```
3. Store Slack token in Knox: `knox set slack-bots/{name}/bot-token --from-env SLACK_BOT_TOKEN`
4. Add as service in Railway `slack-bots` project
5. Add `.taskr/bot.yaml` with identity + review config
6. Update this file
