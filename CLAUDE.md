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

## Consumers
All AIC bots depend on this: wrike-bot, meridian-bot, sable-bot, ciso-bot.
