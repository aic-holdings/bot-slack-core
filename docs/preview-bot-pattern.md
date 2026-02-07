# Preview Bot Pattern

A versioning strategy for Slack bots where stable and preview versions run side-by-side, similar to how Anthropic versions their models (Claude 3.5 Sonnet → Claude 4 Sonnet).

## The Idea

| Bot | Purpose | Audience |
|-----|---------|----------|
| `@Meridian` | Stable v1 — production, reliable | Everyone |
| `@Meridian Preview` | Next version — new features, may break | Opt-in testers |

Users interact with Preview by @mentioning it instead of the stable bot. Both run simultaneously. When Preview is validated, it becomes the new stable version and a new Preview is spun up for the next cycle.

## Why This Pattern

- **Zero-risk feature testing** — Preview can break without affecting production users
- **Real user feedback** — Testers use Preview in actual workflows, not a staging channel
- **Clean promotion path** — When Preview is ready, swap it to become the new stable version
- **Version numbering** — Users can see which version they're talking to (e.g., "Meridian v1" vs "Meridian v2 Preview")

## Architecture

```
Same GitHub repo (e.g., aic-holdings/meridian-bot)
├── main branch ──────────► Railway Service: meridian-stable
│                            Slack App: "Meridian"
│                            SLACK_BOT_TOKEN=xoxb-stable-...
│                            SLACK_APP_TOKEN=xapp-stable-...
│                            BOT_VERSION=1
│
└── preview branch ───────► Railway Service: meridian-preview
                             Slack App: "Meridian Preview"
                             SLACK_BOT_TOKEN=xoxb-preview-...
                             SLACK_APP_TOKEN=xapp-preview-...
                             BOT_VERSION=2
```

Both services run from the **same codebase** but:
- Different Slack apps (separate bot users in the workspace)
- Different Railway services (separate deploys, env vars, logs)
- Different branches (`main` for stable, `preview` for next version)

## Setup Steps

### 1. Create a Second Slack App

In the Slack workspace, create a new app alongside the existing one:

- **Existing app:** "Meridian" (stable)
- **New app:** "Meridian Preview"

Give it the same scopes and event subscriptions. Use a different icon or color to visually distinguish it (e.g., add a "Preview" badge or use a different color scheme).

### 2. Create a Second Railway Service

Same repo, different branch and env vars:

```bash
# In Railway dashboard or CLI:
# - New service in the same project
# - Source: same GitHub repo
# - Branch: preview
# - Environment variables: the Preview Slack app's tokens
```

### 3. Configure with BotConfig

```python
import os

version = os.environ.get("BOT_VERSION", "1")
is_preview = os.environ.get("BOT_PREVIEW", "false").lower() == "true"

config = BotConfig(
    bot_name="Meridian Preview" if is_preview else "Meridian",
    version=f"{version}.0.0-preview" if is_preview else f"{version}.0.0",
    system_prompt="...",
    status_channel="C08B64J5G7N",
)
```

### 4. Optional: Limit Preview to Specific Channels

During early testing, you may want Preview to only respond in certain channels. This isn't built into bot-core yet but can be done at the bot level:

```python
PREVIEW_CHANNELS = os.environ.get("PREVIEW_CHANNELS", "").split(",")

@app.event("app_mention")
def handle(event, say):
    if is_preview and PREVIEW_CHANNELS and event["channel"] not in PREVIEW_CHANNELS:
        return  # Silently ignore mentions outside allowed channels
    # ... normal handling
```

## Version Lifecycle

```
v1 Stable ◄── users depend on this
v2 Preview ◄── testers try new features here

When v2 is validated:
  v2 Preview → becomes v2 Stable (swap tokens/branch)
  v3 Preview → new preview spun up

Version history:
  @Meridian       v1 → v2 → v3 → ...
  @Meridian Preview   v2 → v3 → v4 → ...
```

### Promotion Checklist

When promoting Preview to Stable:

1. Merge `preview` branch into `main`
2. Update `BOT_VERSION` env var on the stable Railway service
3. Verify stable service is healthy
4. Reset `preview` branch from `main` for next cycle
5. Update `BOT_VERSION` on preview Railway service to next version

## Environment Variables

| Variable | Stable | Preview |
|----------|--------|---------|
| `SLACK_BOT_TOKEN` | Stable app token | Preview app token |
| `SLACK_APP_TOKEN` | Stable app token | Preview app token |
| `BOT_VERSION` | `1` | `2` |
| `BOT_PREVIEW` | `false` | `true` |
| `PREVIEW_CHANNELS` | (not set) | `C123,C456` (optional) |

All other env vars (DB, API keys, etc.) can be shared or separate depending on whether Preview needs its own data isolation.

## Naming Convention

| Bot | Slack App Name | Railway Service |
|-----|---------------|-----------------|
| Meridian | Meridian | meridian-stable |
| Meridian Preview | Meridian Preview | meridian-preview |
| CISO | CISO | ciso-stable |
| CISO Preview | CISO Preview | ciso-preview |

## Future: Core Library Support

When this pattern is adopted across bots, consider adding to `bot-core`:

- `BotConfig.is_preview` field
- `BotConfig.allowed_channels` for channel restrictions
- Diagnostic info showing preview status
- A `promote()` CLI command or skillflow for the swap process
