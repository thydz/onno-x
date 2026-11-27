"""Tests for auto-verify, parallel read-only tools and draft recovery."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from onno_x import persistence
from onno_x.config import Config, ModelSpec
from onno_x.session import AgentSession


def _session(edited_file=None):
    cfg = Config(
        active_model="test",
        models={"test": ModelSpec(name="test", provider="openai", model_id="m")},
    )
    session = AgentSession(cfg)
    if edited_file:
        session.turn_edited_paths = [str(edited_file)]
    return session


class _TwoReadProvider:
    """Calls the same read-only tool twice in one assistant message."""

    def __init__(self, path):
        self.path = path
        self.calls = 0

    def chat(self, messages, tools, on_chunk=None):
        self.calls += 1
        if self.calls == 1:
            return "", [
                {"id": "r1", "name": "read_file", "arguments": {"path": self.path}},
                {"id": "r2", "name": "list_dir", "arguments": {"path": "."}},
            ]
        return "done", []


class _EditProvider:
    """Writes a file, then finishes the turn."""

    def __init__(self, path):
        self.path = path
        self.calls = 0

    def chat(self, messages, tools, on_chunk=None):
        self.calls += 1
        if self.calls == 1:
            return "", [
                {
                    "id": "w1",
                    "name": "write_file",
                    "arguments": {"path": self.path, "content": "hello"},
                }
            ]
        return "selesai", []


class ParallelToolTests(unittest.TestCase):
    def test_consecutive_readonly_calls_form_one_group(self):
        session = _session()
        calls = [
            {"id": "a", "name": "read_file", "arguments": {"path": "x"}},
            {"id": "b", "name": "grep_search", "arguments": {"pattern": "y"}},
            {"id": "c", "name": "write_file", "arguments": {"path": "z"}},
            {"id": "d", "name": "read_file", "arguments": {"path": "w"}},
        ]
        self.assertEqual(session._parallel_readonly_groups(calls), [[0, 1]])

    def test_manual_mode_never_parallelises(self):
        session = _session()
        session.permission_mode = "manual"
        calls = [
            {"id": "a", "name": "read_file", "arguments": {"path": "x"}},
            {"id": "b", "name": "read_file", "arguments": {"path": "y"}},
        ]
        self.assertEqual(session._parallel_readonly_groups(calls), [])

    def test_parallel_reads_still_answer_every_call_in_order(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("isi", encoding="utf-8")
            session = _session()
            session.provider = _TwoReadProvider(str(target))

            with mock.patch("onno_x.session.save_session", lambda **kwargs: None):
                session.run_turn("baca", on_output=lambda _r: None)

            tool_msgs = [m for m in session.messages if m.get("role") == "tool"]
            self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["r1", "r2"])
            self.assertIn("isi", tool_msgs[0]["content"])


class AutoVerifyTests(unittest.TestCase):
    def test_verify_runs_after_edit_turn(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.txt"
            session = _session()
            session.provider = _EditProvider(str(target))

            with mock.patch("onno_x.session.save_session", lambda **kwargs: None), \
                 mock.patch("onno_x.commands.detect_test_command", lambda *a, **k: "pytest -q"), \
                 mock.patch("onno_x.commands.detect_lint_command", lambda *a, **k: None), \
                 mock.patch(
                     "onno_x.commands.run_shell_capture",
                     return_value=(0, "1 passed"),
                 ) as runner:
                session.run_turn("tulis", on_output=lambda _r: None)

            self.assertTrue(runner.called)
            self.assertEqual(session.last_verify["command"], "pytest -q")
            self.assertEqual(session.last_verify["returncode"], 0)
            self.assertTrue(target.exists())

    def test_verify_skipped_when_disabled(self):
        session = _session(edited_file="whatever.py")
        session.config.auto_verify = False
        with mock.patch("onno_x.commands.detect_test_command", lambda *a, **k: "pytest"):
            self.assertIsNone(session._auto_verify(on_output=lambda _r: None))

    def test_verify_skipped_without_edits(self):
        session = _session()
        with mock.patch("onno_x.commands.detect_test_command", lambda *a, **k: "pytest"):
            self.assertIsNone(session._auto_verify(on_output=lambda _r: None))

    def test_verify_skipped_when_no_command_detected(self):
        session = _session(edited_file="x.py")
        with mock.patch("onno_x.commands.detect_test_command", lambda *a, **k: None), \
             mock.patch("onno_x.commands.detect_lint_command", lambda *a, **k: None):
            self.assertIsNone(session._auto_verify(on_output=lambda _r: None))


class DraftTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.draft = Path(self._tmp.name) / "draft.json"
        self._patch = mock.patch.object(persistence, "DRAFT_FILE", self.draft)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_roundtrip_same_working_dir(self):
        self.assertTrue(persistence.save_draft("perbaiki test", cwd="/tmp/proj"))
        draft = persistence.load_draft(cwd="/tmp/proj")
        self.assertEqual(draft["text"], "perbaiki test")

    def test_draft_from_other_project_is_not_offered(self):
        persistence.save_draft("lain", cwd="/tmp/other")
        self.assertIsNone(persistence.load_draft(cwd="/tmp/proj"))

    def test_empty_text_is_not_saved(self):
        self.assertFalse(persistence.save_draft("   ", cwd="/tmp/proj"))
        self.assertIsNone(persistence.load_draft(cwd="/tmp/proj"))

    def test_clear_removes_draft(self):
        persistence.save_draft("x", cwd="/tmp/proj")
        self.assertTrue(persistence.clear_draft())
        self.assertIsNone(persistence.load_draft(cwd="/tmp/proj"))
        self.assertFalse(persistence.clear_draft())

    def test_corrupt_draft_is_ignored(self):
        self.draft.write_text("{not json", encoding="utf-8")
        self.assertIsNone(persistence.load_draft(cwd="/tmp/proj"))


if __name__ == "__main__":
    unittest.main()
