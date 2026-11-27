"""Regression tests for filename traversal guards.

Both session ids and skill names become filenames on disk. Session ids arrive
from the CLI (`/resume`) and the web API; skill names can come from the
frontmatter of a remote SKILL.md (`/skill install <url>`). Neither may escape
its own directory.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x import persistence, skills


class SessionIdTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions_dir = Path(self._tmp.name) / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._patch = mock.patch.object(
            persistence, "get_sessions_dir", lambda project_dir=None: self.sessions_dir
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_traversal_ids_are_rejected(self):
        for bad in ("../../etc/passwd", "..\\..\\evil", "a/b", ".hidden", "", "  "):
            with self.subTest(session_id=bad):
                self.assertIsNone(persistence.sanitize_session_id(bad))
                self.assertIsNone(persistence.load_session(bad))

    def test_load_session_cannot_read_outside_sessions_dir(self):
        secret = Path(self._tmp.name) / "secret.json"
        secret.write_text(json.dumps({"messages": [{"role": "user", "content": "LEAK"}]}))
        rel = "../secret"
        self.assertIsNone(persistence.load_session(rel))

    def test_save_session_rejects_bad_id(self):
        with self.assertRaises(ValueError):
            persistence.save_session("../evil", [], "m", 1)

    def test_valid_id_round_trips(self):
        persistence.save_session("sess_20260101_000000", [{"role": "user", "content": "hi"}], "m", 1)
        loaded = persistence.load_session("sess_20260101_000000")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["messages"][0]["content"], "hi")

    def test_delete_session_rejects_bad_id(self):
        self.assertFalse(persistence.delete_session("../../evil"))


class SkillNameTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.global_dir = self.root / "skills"
        self._patches = [
            mock.patch.object(skills, "GLOBAL_SKILLS_DIR", self.global_dir),
            mock.patch.object(skills, "local_dot_skills_dir", lambda: self.root / "local"),
            mock.patch.object(skills, "repo_skills_dir", lambda: self.root / "repo"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_add_skill_rejects_traversal(self):
        for bad in ("../../evil", "..\\evil", "/tmp/evil", ".hidden", "a/b"):
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    skills.add_skill(bad, "# payload")

    def test_add_skill_writes_inside_skills_dir(self):
        path = skills.add_skill("good-skill", "# body")
        self.assertEqual(path.parent, self.global_dir)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "good-skill.md")

    def test_delete_skill_rejects_traversal(self):
        target = self.root / "victim.md"
        target.write_text("keep me")
        self.assertFalse(skills.delete_skill("../../victim"))
        self.assertTrue(target.exists())

    def test_frontmatter_name_cannot_escape(self):
        skill_dir = self.root / "scan" / "safe-dir"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: ../../evil\ndescription: test\n---\n\nbody\n",
            encoding="utf-8",
        )
        parsed = skills.parse_skill_file(skill_dir / "SKILL.md", "repo")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.name, "SKILL")  # falls back to a safe derived name
        self.assertNotIn("/", parsed.name)


if __name__ == "__main__":
    unittest.main()
