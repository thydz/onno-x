"""Session files are rewritten every turn; a torn write must never happen."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x import persistence


class AtomicSessionWriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "sessions"
        self.dir.mkdir(parents=True)
        self._patch = mock.patch.object(persistence, "get_sessions_dir", lambda *a, **k: self.dir)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _save(self, sid, content="hi"):
        return persistence.save_session(
            sid,
            [{"role": "user", "content": content}],
            "m",
            1,
        )

    def test_write_is_private_and_leaves_no_temp_files(self):
        path = self._save("sess_20260101_000000")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(mode, 0o600)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["messages"][0]["content"], "hi")
        self.assertEqual([p.name for p in self.dir.iterdir()], [path.name])

    def test_failed_write_keeps_previous_file_intact(self):
        path = self._save("sess_20260101_000000", "first")

        with mock.patch.object(persistence.json, "dumps", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._save("sess_20260101_000000", "second")

        # Old content survived and no half-written temp file is left behind.
        self.assertEqual(json.loads(path.read_text())["messages"][0]["content"], "first")
        self.assertEqual([p.name for p in self.dir.iterdir()], [path.name])

    def test_failed_replace_cleans_up_temp_file(self):
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self._save("sess_20260101_000000")

        self.assertEqual(list(self.dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
