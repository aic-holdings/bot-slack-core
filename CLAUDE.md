# Bot Core Library

Before making changes, read the `.taskr/` folder:
- `.taskr/service.yaml` — service identity, owner, deploy target
- `.taskr/govern.yaml` — constraints, boundaries, required approvals
- `.taskr/ship.yaml` — branching strategy, CI/CD, release config

## Architecture (v0.5.0)

**AI is the core, human interface is the adapter.**

- `bot_core/ai.py` — OpenRouterClient (built-in AI with tool-use, token logging, X-Title)
- `bot_core/runner.py` — BotRunner + BotConfig (orchestrates AI + adapter)
- `bot_core/slack_adapter.py` — SlackAdapter (Slack Socket Mode, event routing)
- `bot_core/utils.py` — thread history, conversation building, status messages
- `bot_core/scanner.py` — channel scanning, bot conversation extraction
- `bot_core/eval.py` — EvalRunner for golden dataset testing (assertions, token capture, regression detection)

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

## Headless Testing

BotRunner accepts any adapter. Pass a no-op adapter to test without Slack:

```python
class HeadlessAdapter:
    def start(self, runner): pass

runner = BotRunner(config=config, adapter=HeadlessAdapter())
response = runner.handle_message("search for tasks about MCP", [
    {"role": "user", "content": "search for tasks about MCP"}
])
```

This calls the real AI + real tools — the only thing missing is Slack. Use this for stress tests, regression tests, and token measurement. Pull env vars from Railway (`railway variables` or Railway MCP `list-variables`) since secrets live there, not in local .env files.

## Eval Infrastructure

Each bot stores golden test cases in `evals/golden.jsonl`. EvalRunner runs them headless:

```python
from bot_core.eval import EvalRunner

eval_runner = EvalRunner(runner)
cases = eval_runner.load_cases("evals/golden.jsonl", tags=["search"])
report = eval_runner.run(cases)
print(report.summary())

# Compare against baseline
baseline = EvalReport.from_dict(json.load(open("evals/baseline.json")))
diff = report.compare(baseline)
# diff = {pass_rate_delta, token_delta, regressions: [...], improvements: [...]}
```

Golden dataset format (JSONL, one case per line):
```json
{"id": "search-basic", "input": "search for tasks about MCP", "assertions": [{"type": "tool_called", "tool": "search_tasks"}, {"type": "no_error"}], "tags": ["search"]}
```

Assertion types: `tool_called`, `tool_not_called`, `response_contains`, `response_not_contains`, `no_error`, `max_tokens`.

Token capture is non-invasive — attaches a logging handler during eval to parse ai.py's log output. No changes to ai.py needed.

## BotBot Quality Review

BotBot reviews real Slack conversations to find bugs and quality issues. It uses `bot_core/scanner.py` to pull conversations, then sends them to a second-opinion AI (GPT-4o via OpenRouter) for analysis.

### How It Works

```
review-bot                     improve-bot
─────────────────              ─────────────────
scan conversations       →     read BotBot findings
analyze with GPT-4o      →     add golden test cases
record devlog findings   →     run baseline evals
triage by severity       →     make one change
                               re-run evals
                               ship if improved
```

### Running a Review

```bash
cd /path/to/taskr
WRIKE_BOT_SLACK_BOT_TOKEN=xoxb-... OPENROUTER_API_KEY=sk-or-... \
  python -m botbot.run_review wrike-bot
```

- `--since-last-run` — only review new conversations since last BotBot run
- `--max-threads 5` — limit number of threads to review
- `--channel C0ADN7SHY1L` — override channel to scan

### Channel Discovery (no channels:read needed)

Bots don't need `channels:read` scope. Each bot's config in `taskr/botbot/config.py` lists known channel IDs in `scan_channels`. BotBot uses the bot's own token with `channels:history` to pull messages.

### Scanner API (bot_core/scanner.py)

```python
from bot_core.scanner import get_bot_conversations, get_channel_history

# Pull all threads where a bot participated
conversations = get_bot_conversations(
    slack_token="xoxb-...",
    channel="C0ADN7SHY1L",
    bot_user_id="U0ADSPBMVEY",
    oldest="1770552700.0",  # Unix timestamp — only messages after this
    limit=50,
)

# Each conversation: {channel, thread_ts, permalink, messages, bot_user_id}
```

### Findings → Fixes Workflow

1. BotBot records findings as taskr devlogs (tagged `botbot`, `severity-{level}`)
2. Each finding has a devlog ID
3. Pass the devlog ID to `improve-bot` skillflow as the `finding` input
4. `improve-bot` adds golden test cases, runs evals, makes one change, verifies

### Bot Configs

| Bot | Channel | Config function |
|-----|---------|----------------|
| wrike-bot | C0ADN7SHY1L (private) | `get_wrike_bot_config()` |
| meridian | auto-discover | `get_meridian_config()` |

To add a new bot: add a `get_{name}_config()` function in `taskr/botbot/config.py` with the bot's Slack user ID, token env var, known channels, and review focus areas.

## Consumers
All AIC bots depend on this: wrike-bot, meridian-bot, sable-bot, ciso-bot.
