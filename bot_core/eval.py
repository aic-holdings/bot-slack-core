"""
Bot evaluation infrastructure — run golden test cases against a BotRunner.

Captures token usage and tool calls via log interception (no changes to ai.py).
Each bot repo stores its own golden dataset in evals/golden.jsonl.

Usage:
    from bot_core.eval import EvalRunner

    runner = BotRunner(config=config, adapter=HeadlessAdapter())
    eval_runner = EvalRunner(runner)
    cases = eval_runner.load_cases("evals/golden.jsonl")
    report = eval_runner.run(cases)
    print(report.summary())
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EvalCase:
    """A single golden test case."""

    id: str
    input: str
    assertions: List[Dict[str, str]]
    tags: List[str] = field(default_factory=list)
    context: Optional[List[Dict]] = None  # prior messages for multi-turn


@dataclass
class CaseResult:
    """Result from running a single eval case."""

    case_id: str
    passed: bool
    response: str
    assertion_results: List[Dict[str, Any]]
    error: Optional[str]
    elapsed_seconds: float
    tokens: Dict[str, int]
    tool_calls: List[Dict[str, Any]]


@dataclass
class EvalReport:
    """Aggregate results from an eval run."""

    bot_name: str
    model: str
    timestamp: str
    cases: List[CaseResult]
    total_tokens: Dict[str, int]
    pass_rate: float
    duration_seconds: float

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Eval: {self.bot_name} ({self.model})",
            f"Pass rate: {self.pass_rate:.0f}% ({sum(1 for c in self.cases if c.passed)}/{len(self.cases)})",
            f"Tokens: {self.total_tokens.get('total', 0):,}",
            f"Duration: {self.duration_seconds:.1f}s",
        ]
        for case in self.cases:
            status = "PASS" if case.passed else "FAIL"
            lines.append(
                f"  [{status}] {case.case_id} "
                f"({case.elapsed_seconds:.1f}s, {case.tokens.get('total', 0)}t)"
            )
            for ar in case.assertion_results:
                if not ar["passed"]:
                    lines.append(f"         FAILED: {ar['detail']}")
        return "\n".join(lines)

    def compare(self, baseline: "EvalReport") -> Dict[str, Any]:
        """Compare this report against a baseline."""
        baseline_map = {c.case_id: c for c in baseline.cases}
        regressions: List[str] = []
        improvements: List[str] = []

        for case in self.cases:
            bl = baseline_map.get(case.case_id)
            if bl is None:
                continue
            if bl.passed and not case.passed:
                regressions.append(case.case_id)
            elif not bl.passed and case.passed:
                improvements.append(case.case_id)

        return {
            "pass_rate_delta": self.pass_rate - baseline.pass_rate,
            "token_delta": {
                k: self.total_tokens.get(k, 0) - baseline.total_tokens.get(k, 0)
                for k in ("prompt", "completion", "total")
            },
            "regressions": regressions,
            "improvements": improvements,
            "baseline_pass_rate": baseline.pass_rate,
            "current_pass_rate": self.pass_rate,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "bot_name": self.bot_name,
            "model": self.model,
            "timestamp": self.timestamp,
            "pass_rate": self.pass_rate,
            "total_tokens": self.total_tokens,
            "duration_seconds": self.duration_seconds,
            "cases": [
                {
                    "case_id": c.case_id,
                    "passed": c.passed,
                    "response": c.response[:500],
                    "assertion_results": c.assertion_results,
                    "error": c.error,
                    "elapsed_seconds": c.elapsed_seconds,
                    "tokens": c.tokens,
                    "tool_calls": c.tool_calls,
                }
                for c in self.cases
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalReport":
        """Deserialize from a dict (for baseline loading)."""
        cases = [
            CaseResult(
                case_id=c["case_id"],
                passed=c["passed"],
                response=c.get("response", ""),
                assertion_results=c.get("assertion_results", []),
                error=c.get("error"),
                elapsed_seconds=c.get("elapsed_seconds", 0.0),
                tokens=c.get("tokens", {}),
                tool_calls=c.get("tool_calls", []),
            )
            for c in data.get("cases", [])
        ]
        return cls(
            bot_name=data["bot_name"],
            model=data["model"],
            timestamp=data["timestamp"],
            cases=cases,
            total_tokens=data.get("total_tokens", {}),
            pass_rate=data.get("pass_rate", 0.0),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


# ---------------------------------------------------------------------------
# Log capture — non-invasive telemetry from bot_core.ai
# ---------------------------------------------------------------------------

# Patterns from bot_core/ai.py:
#   Line 57: "[Bot Name] tokens: 123p + 45c = 168t"
#   Line 109: "Tool call [1]: name({...})"
_TOKEN_RE = re.compile(r"tokens:\s*(\d+)p\s*\+\s*(\d+)c\s*=\s*(\d+)t")
_TOOL_RE = re.compile(r"Tool call \[(\d+)\]:\s*(\w+)\(")


class _LogCapture(logging.Handler):
    """Captures token and tool call log lines from bot_core.ai."""

    def __init__(self) -> None:
        super().__init__()
        self.tokens: Dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
        self.tool_calls: List[Dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()

        m = _TOKEN_RE.search(msg)
        if m:
            self.tokens["prompt"] += int(m.group(1))
            self.tokens["completion"] += int(m.group(2))
            self.tokens["total"] += int(m.group(3))

        m = _TOOL_RE.search(msg)
        if m:
            self.tool_calls.append({
                "iteration": int(m.group(1)),
                "name": m.group(2),
            })

    def reset(self) -> None:
        self.tokens = {"prompt": 0, "completion": 0, "total": 0}
        self.tool_calls = []


# ---------------------------------------------------------------------------
# Assertion checker
# ---------------------------------------------------------------------------


def _check_assertion(
    assertion: Dict[str, str], response: str, capture: _LogCapture
) -> Dict[str, Any]:
    """Check one assertion against the response and captured telemetry."""
    atype = assertion["type"]

    if atype == "tool_called":
        tool = assertion["tool"]
        called = any(tc["name"] == tool for tc in capture.tool_calls)
        return {
            "type": atype,
            "passed": called,
            "detail": f"{'Found' if called else 'Missing'} call to {tool}",
        }

    if atype == "tool_not_called":
        tool = assertion["tool"]
        called = any(tc["name"] == tool for tc in capture.tool_calls)
        return {
            "type": atype,
            "passed": not called,
            "detail": (
                f"{tool} was called (unexpected)" if called else f"{tool} not called (correct)"
            ),
        }

    if atype == "response_contains":
        text = assertion["text"]
        found = text.lower() in response.lower()
        return {
            "type": atype,
            "passed": found,
            "detail": f"{'Found' if found else 'Missing'} '{text}' in response",
        }

    if atype == "response_not_contains":
        text = assertion["text"]
        found = text.lower() in response.lower()
        return {
            "type": atype,
            "passed": not found,
            "detail": (
                f"'{text}' found (unexpected)" if found else f"'{text}' absent (correct)"
            ),
        }

    if atype == "no_error":
        return {"type": atype, "passed": True, "detail": "No exception thrown"}

    if atype == "max_tokens":
        budget = int(assertion["budget"])
        actual = capture.tokens["total"]
        return {
            "type": atype,
            "passed": actual <= budget,
            "detail": f"Tokens: {actual} {'<=' if actual <= budget else '>'} {budget} budget",
        }

    return {"type": atype, "passed": False, "detail": f"Unknown assertion type: {atype}"}


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------


class EvalRunner:
    """Runs eval cases against a BotRunner and produces an EvalReport."""

    def __init__(self, runner: Any) -> None:
        self.runner = runner

    def load_cases(
        self, jsonl_path: str, tags: Optional[List[str]] = None
    ) -> List[EvalCase]:
        """Load cases from a JSONL file, optionally filtered by tags."""
        cases: List[EvalCase] = []
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                case = EvalCase(
                    id=data["id"],
                    input=data["input"],
                    assertions=data["assertions"],
                    tags=data.get("tags", []),
                    context=data.get("context"),
                )
                if tags and not any(t in case.tags for t in tags):
                    continue
                cases.append(case)
        return cases

    def run_case(self, case: EvalCase) -> CaseResult:
        """Run a single eval case."""
        ai_logger = logging.getLogger("bot_core.ai")
        capture = _LogCapture()
        ai_logger.addHandler(capture)

        start = time.time()
        try:
            messages: List[Dict] = []
            if case.context:
                messages.extend(case.context)
            messages.append({"role": "user", "content": case.input})

            response = self.runner.handle_message(case.input, messages)
            elapsed = time.time() - start

            assertion_results = [
                _check_assertion(a, response, capture) for a in case.assertions
            ]
            all_passed = all(r["passed"] for r in assertion_results)

            return CaseResult(
                case_id=case.id,
                passed=all_passed,
                response=response,
                assertion_results=assertion_results,
                error=None,
                elapsed_seconds=elapsed,
                tokens=dict(capture.tokens),
                tool_calls=list(capture.tool_calls),
            )
        except Exception as e:
            elapsed = time.time() - start
            # no_error assertions should fail when an exception occurs
            assertion_results = []
            for a in case.assertions:
                if a["type"] == "no_error":
                    assertion_results.append({
                        "type": "no_error",
                        "passed": False,
                        "detail": f"Exception: {e}",
                    })
                else:
                    assertion_results.append(
                        _check_assertion(a, "", capture)
                    )

            return CaseResult(
                case_id=case.id,
                passed=False,
                response="",
                assertion_results=assertion_results,
                error=str(e),
                elapsed_seconds=elapsed,
                tokens=dict(capture.tokens),
                tool_calls=list(capture.tool_calls),
            )
        finally:
            ai_logger.removeHandler(capture)

    def run(self, cases: List[EvalCase]) -> EvalReport:
        """Run all cases and produce an EvalReport."""
        run_start = time.time()
        results = [self.run_case(case) for case in cases]
        duration = time.time() - run_start

        total_tokens: Dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
        for r in results:
            for k in total_tokens:
                total_tokens[k] += r.tokens.get(k, 0)

        passed = sum(1 for r in results if r.passed)
        pass_rate = (passed / len(results) * 100) if results else 0.0

        return EvalReport(
            bot_name=self.runner.config.bot_name,
            model=self.runner.config.model or "unknown",
            timestamp=datetime.now(timezone.utc).isoformat(),
            cases=results,
            total_tokens=total_tokens,
            pass_rate=pass_rate,
            duration_seconds=duration,
        )
