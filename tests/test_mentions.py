import os
import tempfile
import unittest
from pathlib import Path


class MentionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src" / "deep").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / ".git").mkdir()
        (root / "node_modules" / "pkg").mkdir(parents=True)
        (root / "src" / "app.py").write_text("print('hi')\n")
        (root / "src" / "deep" / "mod.py").write_text("x = 1\n")
        (root / "docs" / "readme.md").write_text("docs\n")
        (root / ".git" / "config").write_text("git\n")
        (root / "node_modules" / "pkg" / "index.js").write_text("js\n")
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def _names(self, prefix, limit=60):
        from onno_x.mentions import iter_mentions

        return iter_mentions(self.root, prefix, limit=limit)

    def test_empty_prefix_lists_top_level_dirs_first(self):
        entries = self._names("")
        rels = [e[0] for e in entries]
        self.assertEqual(rels[:2], ["docs", "src"])
        self.assertTrue(entries[0][1])
        self.assertNotIn(".git", rels)
        self.assertNotIn("node_modules", rels)

    def test_nested_probe_is_recursive(self):
        rels = [e[0] for e in self._names("ap")]
        self.assertIn("src/app.py", rels)

    def test_trailing_slash_lists_folder_contents(self):
        rels = [e[0] for e in self._names("src/")]
        self.assertIn("src/app.py", rels)
        self.assertIn("src/deep", rels)
        self.assertNotIn("docs/readme.md", rels)

    def test_deep_match_by_basename(self):
        rels = [e[0] for e in self._names("mod")]
        self.assertIn("src/deep/mod.py", rels)

    def test_ignored_dirs_never_listed(self):
        rels = [e[0] for e in self._names("index")]
        self.assertEqual(rels, [])

    def test_limit_is_respected(self):
        for i in range(10):
            (self.root / f"file{i}.txt").write_text("x")
        entries = self._names("file", limit=3)
        self.assertEqual(len(entries), 3)

    def test_missing_root_returns_empty(self):
        from onno_x.mentions import iter_mentions

        self.assertEqual(iter_mentions(self.root / "nope", "x"), [])

    def test_human_size(self):
        from onno_x.mentions import human_size

        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(2048), "2.0 KB")


class ReplMentionCompleterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src" / "sub").mkdir(parents=True)
        (root / "src" / "main.py").write_text("x\n")
        self.root = root
        self.prev = os.getcwd()
        os.chdir(root)

    def tearDown(self):
        os.chdir(self.prev)
        self.tmp.cleanup()

    def _completions(self, text):
        from prompt_toolkit.document import Document

        from onno_x.main import SlashCompleter

        doc = Document(text, cursor_position=len(text))
        return list(SlashCompleter().get_completions(doc, None))

    def test_at_prefix_yields_paths(self):
        comps = self._completions("@sr")
        values = [c.text for c in comps]
        self.assertIn("src/", values)
        self.assertTrue(all(c.display_text.startswith("@") for c in comps))

    def test_at_slash_lists_children(self):
        comps = self._completions("@src/")
        values = [c.text for c in comps]
        self.assertIn("src/main.py", values)
        self.assertIn("src/sub/", values)

    def test_plain_text_has_no_file_completions(self):
        self.assertEqual(self._completions("baca src"), [])


if __name__ == "__main__":
    unittest.main()
