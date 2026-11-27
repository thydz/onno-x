import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x import skills


class CwdSkillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # macOS resolves /var -> /private/var, and os.chdir() settles on the real path.
        self.root = Path(self._tmp.name).resolve()
        self._old_cwd = Path.cwd()
        self._patches = [
            mock.patch.object(skills, "GLOBAL_SKILLS_DIR", self.root / "global"),
            mock.patch.object(skills, "PACKAGE_SKILLS_DIR", self.root / "pkg"),
        ]
        for p in self._patches:
            p.start()
        skills.invalidate_skills_cache()
        self.a = self.root / "project-a"
        self.b = self.root / "project-b"
        self.a.mkdir()
        self.b.mkdir()

    def tearDown(self):
        os.chdir(self._old_cwd)
        for p in self._patches:
            p.stop()
        skills.invalidate_skills_cache()
        self._tmp.cleanup()

    def test_local_skill_dirs_are_resolved_after_chdir(self):
        os.chdir(self.a)
        self.assertEqual(skills.local_dot_skills_dir(), self.a / ".onno-x" / "skills")
        self.assertEqual(skills.repo_skills_dir(), self.a / "skills")

        os.chdir(self.b)
        self.assertEqual(skills.local_dot_skills_dir(), self.b / ".onno-x" / "skills")

    def test_skills_follow_cwd_once_the_cache_is_dropped(self):
        os.chdir(self.a)
        written = skills.add_skill("in-a", "# A", local=True)
        self.assertEqual(written.parent, self.a / ".onno-x" / "skills")
        self.assertIn("in-a", skills.list_skills(force_reload=True))

        os.chdir(self.b)
        # The cached listing still belongs to the previous directory...
        self.assertIn("in-a", skills.list_skills())
        # ...until the cache is dropped (change_directory does this).
        skills.invalidate_skills_cache()
        self.assertNotIn("in-a", skills.list_skills())

        skills.add_skill("in-b", "# B", local=True)
        self.assertIn("in-b", skills.list_skills(force_reload=True))


if __name__ == "__main__":
    unittest.main()
