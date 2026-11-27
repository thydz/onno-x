"""Tests for /sessions search, /resume numbering and /help <command>."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x import persistence
from onno_x.commands import find_command_help


class SessionLookupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "sessions"
        self.dir.mkdir(parents=True)
        self._patch = mock.patch.object(
            persistence, "get_sessions_dir", lambda *a, **k: self.dir
        )
        self._patch.start()
        self._patch_home = mock.patch.object(
            persistence.Path, "home", lambda: Path(self._tmp.name)
        )
        self._patch_home.start()

    def tearDown(self):
        self._patch_home.stop()
        self._patch.stop()
        self._tmp.cleanup()

    def _write(self, sid, title, updated_at, model="gpt-4o", cwd="/tmp/alpha"):
        payload = {
            "session_id": sid,
            "title": title,
            "updated_at": updated_at,
            "model_name": model,
            "cwd": cwd,
            "turns_count": 1,
            "messages": [{"role": "user", "content": title}],
        }
        (self.dir / f"{sid}.json").write_text(json.dumps(payload), encoding="utf-8")

    def _three(self):
        self._write("aaa_newest", "refactor auth", "2026-01-03T10:00:00")
        self._write("bbb_middle", "fix login bug", "2026-01-02T10:00:00")
        self._write("ccc_oldest", "docs pass", "2026-01-01T10:00:00", model="claude")

    def test_resolve_by_number_uses_list_order(self):
        self._three()
        self.assertEqual(persistence.resolve_session_ref("1"), "aaa_newest")
        self.assertEqual(persistence.resolve_session_ref("3"), "ccc_oldest")

    def test_resolve_by_unique_prefix_and_full_id(self):
        self._three()
        self.assertEqual(persistence.resolve_session_ref("bbb"), "bbb_middle")
        self.assertEqual(persistence.resolve_session_ref("ccc_oldest"), "ccc_oldest")

    def test_unknown_or_out_of_range_returns_none(self):
        self._three()
        self.assertIsNone(persistence.resolve_session_ref("9"))
        self.assertIsNone(persistence.resolve_session_ref("zzz"))
        self.assertIsNone(persistence.resolve_session_ref(""))

    def test_search_matches_title_model_and_id(self):
        self._three()
        self.assertEqual(
            [s["id"] for s in persistence.search_sessions("login")], ["bbb_middle"]
        )
        self.assertEqual(
            [s["id"] for s in persistence.search_sessions("claude")], ["ccc_oldest"]
        )
        self.assertEqual(
            [s["id"] for s in persistence.search_sessions("BBB")], ["bbb_middle"]
        )
        self.assertEqual(len(persistence.search_sessions("")), 3)

    def test_search_without_match_is_empty(self):
        self._three()
        self.assertEqual(persistence.search_sessions("nope"), [])


class HelpDetailTests(unittest.TestCase):
    TABLE = [
        ("/cost", "Menampilkan token usage dan biaya"),
        ("/usage", "Alias dari /cost"),
        ("/count", "Menghitung sesuatu"),
    ]

    def test_exact_match_wins(self):
        text = find_command_help(self.TABLE, "/cost")
        self.assertIn("/cost", text)
        self.assertIn("token usage", text)

    def test_leading_slash_optional_and_case_insensitive(self):
        self.assertIsNotNone(find_command_help(self.TABLE, "COST"))

    def test_aliases_listed(self):
        text = find_command_help(self.TABLE, "cost")
        self.assertIn("/usage", text)

    def test_unknown_command_returns_none(self):
        self.assertIsNone(find_command_help(self.TABLE, "nope"))
        self.assertIsNone(find_command_help(self.TABLE, ""))


if __name__ == "__main__":
    unittest.main()
