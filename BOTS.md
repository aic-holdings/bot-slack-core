# AIC Bot Ecosystem

## Naming Convention

Bot repos follow **`{name}-bot`**, the shared library is **`bot-core`**:

| Repo | Bot Name | What It Does |
|------|----------|---|
| [bot-core](https://github.com/aic-holdings/bot-core) | — | Shared library (not a bot). Messaging plumbing, thread history, ChannelScanner. |
| [meridian-bot](https://github.com/aic-holdings/meridian-bot) | Meridian | Trading idea journal. Market data, portfolio analysis, research tools. |
| [sable-bot](https://github.com/aic-holdings/sable-bot) | Sable | Portfolio data queries and risk analysis. |
| [ciso-bot](https://github.com/aic-holdings/ciso-bot) | CISO | Sentinel AI CISO — security posture and compliance. |

## Architecture

```
bot-core (shared library, v0.3.0)
├── BotRunner         — Socket Mode event handler
├── BotConfig         — configuration dataclass
├── ChannelScanner    — thread history for BotBot reviews
└── utils             — thread history, message formatting, status posts

Each bot:
├── Imports bot-core for messaging plumbing
├── Owns its AI client (injected via chat_fn, not in core)
├── Owns its business logic and tools
└── Declares review profile in .taskr/bot.yaml
```

Core principle: **Bots own AI policy. Core owns messaging plumbing.**

## Railway

All bots deploy to a single Railway project: **`slack-bots`**

Each bot is a service inside that project:
- `meridian-bot` — meridian-bot
- `sable-bot` — sable-bot
- `ciso-bot` — ciso-bot (if deployed)

## Knox Secrets

Bot credentials live in Knox under `slack-bots/{bot-name}/`:

```
slack-bots/meridian/bot-token    — Meridian's SLACK_BOT_TOKEN
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

BotBot is **not a bot** — it's a backend review engine that lives in the [taskr](https://github.com/aic-holdings/taskr) monorepo at `botbot/`.

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

## Meridian Exception

**Meridian** is intentionally excluded from the BotRunner pattern. It has a complex agent architecture (`src/agent/`, `src/tools/`, `src/slack/`) with tool-use loops, streaming responses, and financial data integrations that don't fit the simple `chat_fn` contract. It uses slack-bolt directly. This is a deliberate architectural decision, not technical debt.

## Adding a New Bot

1. Create repo: `aic-holdings/{name}-bot`
2. Add `bot-core` from pypiserver in `requirements.txt`:
   ```
   --extra-index-url https://aic-reader:<password>@pypiserver-production.up.railway.app/simple/
   bot-core==0.3.0
   ```
   Reader credentials in Knox: `pypiserver/reader-username`, `pypiserver/reader-password`
3. Store Slack token in Knox: `knox set slack-bots/{name}/bot-token --from-env SLACK_BOT_TOKEN`
4. Add as service in Railway `slack-bots` project
5. Add `.taskr/bot.yaml` with identity + review config
6. Update this file
