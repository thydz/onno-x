"""Regressions for the ways a turn could die mid-flight.

Three separate faults used to end the session with no trace:

1. Rich raised MarkupError on untrusted "[" text during compositor reflow.
2. The TUI worker's try block only wrapped the agent turn, so an exception in
   any slash-command branch killed the worker with is_running_turn left True.
3. `str.isdigit()` accepts '²', which `int()` then rejects.
"""
import io
import unittest

import onno_x.ui  # noqa: F401  installs the tolerant-markup patch
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

POISON = "[/google.*\\.js/,/facebook.*\\.js/,/analytics.*\\.js/,/gtag.*\\.js/,/doubleclick/,/adsense/]"


def _console() -> Console:
    return Console(file=io.StringIO(), width=100)


class MarkupSafetyTests(unittest.TestCase):
    def test_untrusted_body_renders_as_text(self) -> None:
        lines = f"1. [x] done\n2. [ ] {POISON}"
        _console().print(Panel(Text("\n".join(lines)), title="Todo (2)"))

    def test_untrusted_title_is_escaped(self) -> None:
        for title in (
            f"grep: {escape(POISON)} (1 baris)",
            f"find: {escape(POISON)} (1 file)",
            f"git stash {escape(POISON)}",
        ):
            _console().print(Panel(Text("ok"), title=title))

    def test_raw_body_no_longer_crashes(self) -> None:
        # The tolerant-markup patch means a future call site that forgets
        # Text()/escape() degrades to plain text instead of killing the app.
        _console().print(Panel(f"2. [ ] {POISON}"))

    def test_fstring_and_table_cells_survive(self) -> None:
        c = _console()
        c.print(f"[yellow]no match '{POISON}'[/yellow]")
        table = Table(title=f"t {POISON}")
        table.add_column("a")
        table.add_row(POISON)
        c.print(table)

    def test_valid_markup_still_renders(self) -> None:
        text = Text.from_markup("[bold red]x[/bold red]")
        self.assertEqual(text.plain, "x")


class NumericGuardTests(unittest.TestCase):
    def test_isdecimal_rejects_superscript(self) -> None:
        # isdigit() returns True for '²', int('²') raises ValueError.
        self.assertTrue("²".isdigit())
        self.assertFalse("²".isdecimal())
        self.assertEqual(int("٣"), 3)


class WorkerKeepsUiAliveTests(unittest.TestCase):
    def test_worker_crash_resets_busy_flag(self) -> None:
        from onno_x.tui import OnnoXUI

        class Fake:
            def __init__(self) -> None:
                self.is_running_turn = False
                self.calls = []

            def _dispatch_agent_turn(self, _msg: str) -> None:
                raise RuntimeError("boom in a slash branch")

            def safe_call_from_thread(self, fn, *args):
                self.calls.append(fn.__name__)

            def print_tool_result(self, *args):
                pass

            def stop_activity_ticker(self) -> None:
                pass

            def update_status(self) -> None:
                pass

        raw = OnnoXUI.dispatch_agent_turn.__wrapped__
        fake = Fake()
        raw(fake, "hello")

        self.assertFalse(fake.is_running_turn)
        self.assertIn("print_tool_result", fake.calls)
        self.assertIn("stop_activity_ticker", fake.calls)


class TruncationContinuationTests(unittest.TestCase):
    """A reply cut off at max_tokens must be resumed, not committed as final."""

    def _session(self, provider_cls):
        from onno_x.config import Config, ModelSpec
        from onno_x.session import AgentSession

        spec = ModelSpec(name="x", provider="openai", model_id="m")
        config = Config(models={"x": spec}, active_model="x")
        config.max_steps = 20
        session = AgentSession(config)
        session.provider = provider_cls(spec)
        return session

    def test_truncation_is_continued_then_capped(self) -> None:
        from onno_x.providers.base import BaseProvider

        class AlwaysTruncated(BaseProvider):
            calls = 0

            def chat(self, messages, tools, on_chunk=None, cancel_event=None):
                AlwaysTruncated.calls += 1
                self.last_truncated = True
                if on_chunk:
                    on_chunk("part")
                return "part", []

        AlwaysTruncated.calls = 0
        session = self._session(AlwaysTruncated)
        result = session.run_turn("go", on_output=lambda _r: None)

        self.assertEqual(AlwaysTruncated.calls, 4)  # initial + 3 continuations
        self.assertEqual(result, "part" * 4)

    def test_complete_reply_is_not_continued(self) -> None:
        from onno_x.providers.base import BaseProvider

        class Complete(BaseProvider):
            calls = 0

            def chat(self, messages, tools, on_chunk=None, cancel_event=None):
                Complete.calls += 1
                self.last_truncated = False
                return "done", []

        Complete.calls = 0
        session = self._session(Complete)
        result = session.run_turn("go", on_output=lambda _r: None)

        self.assertEqual(Complete.calls, 1)
        self.assertEqual(result, "done")


if __name__ == "__main__":
    unittest.main()
