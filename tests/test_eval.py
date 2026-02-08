"""Tests for bot_core.eval"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from bot_core.eval import (
    CaseResult,
    EvalCase,
    EvalReport,
    EvalRunner,
    _LogCapture,
    _check_assertion,
)


# ---------------------------------------------------------------------------
# _LogCapture tests
# ---------------------------------------------------------------------------


class TestLogCapture:
    def test_parses_token_string(self):
        capture = _LogCapture()
        record = logging.LogRecord(
            "bot_core.ai", logging.INFO, "", 0,
            "[Wrike Bot] tokens: 1703p + 55c = 1758t", (), None,
        )
        capture.emit(record)
        assert capture.tokens == {"prompt": 1703, "completion": 55, "total": 1758}

    def test_accumulates_tokens(self):
        capture = _LogCapture()
        for msg in [
            "[Bot] tokens: 100p + 50c = 150t",
            "[Bot] tokens: 200p + 100c = 300t",
        ]:
            record = logging.LogRecord(
                "bot_core.ai", logging.INFO, "", 0, msg, (), None,
            )
            capture.emit(record)
        assert capture.tokens == {"prompt": 300, "completion": 150, "total": 450}

    def test_parses_tool_call_string(self):
        capture = _LogCapture()
        record = logging.LogRecord(
            "bot_core.ai", logging.INFO, "", 0,
            "Tool call [1]: search_tasks({'query': 'MCP'})", (), None,
        )
        capture.emit(record)
        assert len(capture.tool_calls) == 1
        assert capture.tool_calls[0]["name"] == "search_tasks"
        assert capture.tool_calls[0]["iteration"] == 1

    def test_multiple_tool_calls(self):
        capture = _LogCapture()
        for msg in [
            "Tool call [1]: search_tasks({'query': 'MCP'})",
            "Tool call [2]: get_task({'task_id': 'abc'})",
        ]:
            record = logging.LogRecord(
                "bot_core.ai", logging.INFO, "", 0, msg, (), None,
            )
            capture.emit(record)
        assert len(capture.tool_calls) == 2
        assert capture.tool_calls[0]["name"] == "search_tasks"
        assert capture.tool_calls[1]["name"] == "get_task"

    def test_ignores_unrelated_logs(self):
        capture = _LogCapture()
        record = logging.LogRecord(
            "bot_core.ai", logging.INFO, "", 0,
            "OpenRouter API error: 500", (), None,
        )
        capture.emit(record)
        assert capture.tokens == {"prompt": 0, "completion": 0, "total": 0}
        assert capture.tool_calls == []

    def test_reset(self):
        capture = _LogCapture()
        record = logging.LogRecord(
            "bot_core.ai", logging.INFO, "", 0,
            "[Bot] tokens: 100p + 50c = 150t", (), None,
        )
        capture.emit(record)
        capture.reset()
        assert capture.tokens == {"prompt": 0, "completion": 0, "total": 0}
        assert capture.tool_calls == []


# ---------------------------------------------------------------------------
# Assertion checker tests
# ---------------------------------------------------------------------------


class TestCheckAssertion:
    def _make_capture(self, tool_names=None):
        capture = _LogCapture()
        for name in (tool_names or []):
            capture.tool_calls.append({"iteration": 1, "name": name})
        return capture

    def test_tool_called_pass(self):
        capture = self._make_capture(["search_tasks"])
        result = _check_assertion(
            {"type": "tool_called", "tool": "search_tasks"}, "", capture
        )
        assert result["passed"] is True

    def test_tool_called_fail(self):
        capture = self._make_capture([])
        result = _check_assertion(
            {"type": "tool_called", "tool": "search_tasks"}, "", capture
        )
        assert result["passed"] is False

    def test_tool_not_called_pass(self):
        capture = self._make_capture([])
        result = _check_assertion(
            {"type": "tool_not_called", "tool": "create_task"}, "", capture
        )
        assert result["passed"] is True

    def test_tool_not_called_fail(self):
        capture = self._make_capture(["create_task"])
        result = _check_assertion(
            {"type": "tool_not_called", "tool": "create_task"}, "", capture
        )
        assert result["passed"] is False

    def test_response_contains_pass(self):
        capture = self._make_capture()
        result = _check_assertion(
            {"type": "response_contains", "text": "MCP"},
            "Found 3 tasks about MCP",
            capture,
        )
        assert result["passed"] is True

    def test_response_contains_case_insensitive(self):
        capture = self._make_capture()
        result = _check_assertion(
            {"type": "response_contains", "text": "mcp"},
            "Found tasks about MCP",
            capture,
        )
        assert result["passed"] is True

    def test_response_contains_fail(self):
        capture = self._make_capture()
        result = _check_assertion(
            {"type": "response_contains", "text": "MCP"}, "No results", capture
        )
        assert result["passed"] is False

    def test_response_not_contains_pass(self):
        capture = self._make_capture()
        result = _check_assertion(
            {"type": "response_not_contains", "text": "error"},
            "Here are your tasks",
            capture,
        )
        assert result["passed"] is True

    def test_response_not_contains_fail(self):
        capture = self._make_capture()
        result = _check_assertion(
            {"type": "response_not_contains", "text": "error"},
            "An error occurred",
            capture,
        )
        assert result["passed"] is False

    def test_no_error_pass(self):
        capture = self._make_capture()
        result = _check_assertion({"type": "no_error"}, "All good", capture)
        assert result["passed"] is True

    def test_max_tokens_pass(self):
        capture = self._make_capture()
        capture.tokens["total"] = 3000
        result = _check_assertion(
            {"type": "max_tokens", "budget": "5000"}, "", capture
        )
        assert result["passed"] is True

    def test_max_tokens_fail(self):
        capture = self._make_capture()
        capture.tokens["total"] = 8000
        result = _check_assertion(
            {"type": "max_tokens", "budget": "5000"}, "", capture
        )
        assert result["passed"] is False

    def test_unknown_type(self):
        capture = self._make_capture()
        result = _check_assertion({"type": "magic"}, "", capture)
        assert result["passed"] is False
        assert "Unknown" in result["detail"]


# ---------------------------------------------------------------------------
# EvalRunner tests
# ---------------------------------------------------------------------------


class TestLoadCases:
    def test_loads_jsonl(self, tmp_path):
        golden = tmp_path / "golden.jsonl"
        golden.write_text(
            '{"id": "a", "input": "hello", "assertions": [{"type": "no_error"}], "tags": ["basic"]}\n'
            '{"id": "b", "input": "bye", "assertions": [], "tags": ["other"]}\n'
        )
        runner = EvalRunner(MagicMock())
        cases = runner.load_cases(str(golden))
        assert len(cases) == 2
        assert cases[0].id == "a"
        assert cases[1].id == "b"

    def test_filters_by_tags(self, tmp_path):
        golden = tmp_path / "golden.jsonl"
        golden.write_text(
            '{"id": "a", "input": "x", "assertions": [], "tags": ["search"]}\n'
            '{"id": "b", "input": "y", "assertions": [], "tags": ["safety"]}\n'
            '{"id": "c", "input": "z", "assertions": [], "tags": ["search", "complex"]}\n'
        )
        runner = EvalRunner(MagicMock())
        cases = runner.load_cases(str(golden), tags=["safety"])
        assert len(cases) == 1
        assert cases[0].id == "b"

    def test_skips_blank_lines(self, tmp_path):
        golden = tmp_path / "golden.jsonl"
        golden.write_text(
            '{"id": "a", "input": "x", "assertions": []}\n'
            '\n'
            '{"id": "b", "input": "y", "assertions": []}\n'
        )
        runner = EvalRunner(MagicMock())
        cases = runner.load_cases(str(golden))
        assert len(cases) == 2

    def test_loads_context(self, tmp_path):
        golden = tmp_path / "golden.jsonl"
        golden.write_text(
            '{"id": "a", "input": "details", "assertions": [], "context": [{"role": "user", "content": "search mcp"}, {"role": "assistant", "content": "found 3"}]}\n'
        )
        runner = EvalRunner(MagicMock())
        cases = runner.load_cases(str(golden))
        assert cases[0].context is not None
        assert len(cases[0].context) == 2


class TestRunCase:
    def test_passing_case(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.return_value = "Found 3 MCP tasks"

        eval_runner = EvalRunner(mock_runner)
        case = EvalCase(
            id="test",
            input="search MCP",
            assertions=[{"type": "response_contains", "text": "MCP"}],
        )
        result = eval_runner.run_case(case)
        assert result.passed is True
        assert result.error is None

    def test_failing_case(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.return_value = "No results"

        eval_runner = EvalRunner(mock_runner)
        case = EvalCase(
            id="test",
            input="search MCP",
            assertions=[{"type": "response_contains", "text": "MCP"}],
        )
        result = eval_runner.run_case(case)
        assert result.passed is False

    def test_exception_marks_no_error_failed(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.side_effect = RuntimeError("boom")

        eval_runner = EvalRunner(mock_runner)
        case = EvalCase(
            id="test",
            input="hello",
            assertions=[{"type": "no_error"}],
        )
        result = eval_runner.run_case(case)
        assert result.passed is False
        assert result.error == "boom"
        assert result.assertion_results[0]["passed"] is False

    def test_handler_cleaned_up_on_success(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.return_value = "ok"

        ai_logger = logging.getLogger("bot_core.ai")
        handlers_before = len(ai_logger.handlers)

        eval_runner = EvalRunner(mock_runner)
        eval_runner.run_case(EvalCase(id="t", input="x", assertions=[]))

        assert len(ai_logger.handlers) == handlers_before

    def test_handler_cleaned_up_on_error(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.side_effect = RuntimeError("boom")

        ai_logger = logging.getLogger("bot_core.ai")
        handlers_before = len(ai_logger.handlers)

        eval_runner = EvalRunner(mock_runner)
        eval_runner.run_case(EvalCase(id="t", input="x", assertions=[]))

        assert len(ai_logger.handlers) == handlers_before

    def test_builds_messages_with_context(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.return_value = "ok"

        eval_runner = EvalRunner(mock_runner)
        case = EvalCase(
            id="t",
            input="details on the first one",
            assertions=[],
            context=[
                {"role": "user", "content": "search MCP"},
                {"role": "assistant", "content": "Found 3 tasks"},
            ],
        )
        eval_runner.run_case(case)

        call_args = mock_runner.handle_message.call_args
        messages = call_args[0][1]
        assert len(messages) == 3  # 2 context + 1 new
        assert messages[0]["role"] == "user"
        assert messages[2]["content"] == "details on the first one"


class TestRunAll:
    def test_produces_report(self):
        mock_runner = MagicMock()
        mock_runner.handle_message.return_value = "ok"
        mock_runner.config.bot_name = "Test Bot"
        mock_runner.config.model = "test-model"

        eval_runner = EvalRunner(mock_runner)
        cases = [
            EvalCase(id="a", input="x", assertions=[{"type": "no_error"}]),
            EvalCase(id="b", input="y", assertions=[{"type": "no_error"}]),
        ]
        report = eval_runner.run(cases)
        assert report.bot_name == "Test Bot"
        assert report.pass_rate == 100.0
        assert len(report.cases) == 2


# ---------------------------------------------------------------------------
# EvalReport tests
# ---------------------------------------------------------------------------


class TestEvalReportCompare:
    def _make_report(self, case_results, tokens=None):
        return EvalReport(
            bot_name="Test",
            model="test",
            timestamp="2026-01-01T00:00:00",
            cases=case_results,
            total_tokens=tokens or {"prompt": 0, "completion": 0, "total": 0},
            pass_rate=sum(1 for c in case_results if c.passed) / len(case_results) * 100 if case_results else 0,
            duration_seconds=1.0,
        )

    def _make_case(self, case_id, passed):
        return CaseResult(
            case_id=case_id,
            passed=passed,
            response="",
            assertion_results=[],
            error=None,
            elapsed_seconds=0.1,
            tokens={"prompt": 0, "completion": 0, "total": 0},
            tool_calls=[],
        )

    def test_detects_regression(self):
        baseline = self._make_report([
            self._make_case("a", True),
            self._make_case("b", True),
        ])
        current = self._make_report([
            self._make_case("a", True),
            self._make_case("b", False),
        ])
        diff = current.compare(baseline)
        assert "b" in diff["regressions"]
        assert diff["improvements"] == []

    def test_detects_improvement(self):
        baseline = self._make_report([
            self._make_case("a", False),
            self._make_case("b", True),
        ])
        current = self._make_report([
            self._make_case("a", True),
            self._make_case("b", True),
        ])
        diff = current.compare(baseline)
        assert "a" in diff["improvements"]
        assert diff["regressions"] == []

    def test_pass_rate_delta(self):
        baseline = self._make_report([
            self._make_case("a", True),
            self._make_case("b", False),
        ])
        current = self._make_report([
            self._make_case("a", True),
            self._make_case("b", True),
        ])
        diff = current.compare(baseline)
        assert diff["pass_rate_delta"] == 50.0

    def test_token_delta(self):
        baseline = self._make_report(
            [self._make_case("a", True)],
            tokens={"prompt": 1000, "completion": 200, "total": 1200},
        )
        current = self._make_report(
            [self._make_case("a", True)],
            tokens={"prompt": 800, "completion": 150, "total": 950},
        )
        diff = current.compare(baseline)
        assert diff["token_delta"]["total"] == -250

    def test_new_case_ignored(self):
        baseline = self._make_report([self._make_case("a", True)])
        current = self._make_report([
            self._make_case("a", True),
            self._make_case("b", False),
        ])
        diff = current.compare(baseline)
        assert diff["regressions"] == []
        assert diff["improvements"] == []


class TestEvalReportSerialization:
    def test_round_trip(self):
        report = EvalReport(
            bot_name="Test",
            model="haiku",
            timestamp="2026-01-01T00:00:00",
            cases=[
                CaseResult(
                    case_id="a",
                    passed=True,
                    response="ok",
                    assertion_results=[{"type": "no_error", "passed": True, "detail": "ok"}],
                    error=None,
                    elapsed_seconds=1.5,
                    tokens={"prompt": 100, "completion": 50, "total": 150},
                    tool_calls=[{"iteration": 1, "name": "search_tasks"}],
                )
            ],
            total_tokens={"prompt": 100, "completion": 50, "total": 150},
            pass_rate=100.0,
            duration_seconds=1.5,
        )
        data = report.to_dict()
        restored = EvalReport.from_dict(data)
        assert restored.bot_name == "Test"
        assert restored.pass_rate == 100.0
        assert len(restored.cases) == 1
        assert restored.cases[0].case_id == "a"
