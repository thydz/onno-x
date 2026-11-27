"""Tests for the second batch of commands (/todo, /snapshot, /alias, /test, ...)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x.commands import (
    detect_lint_command,
    detect_test_command,
    expand_alias,
    find_files,
    git_log,
    git_stash,
    grep_repo,
    token_breakdown,
)
from onno_x.config import Config, ModelSpec
from onno_x.session import AgentSession, build_system_prompt, strip_reasoning


def make_config(**kwargs):
    return Config(
        active_model="test",
        models={"test": ModelSpec(name="test", provider="openai", model_id="m")},
        **kwargs,
    )


class _StubProvider:
    def __init__(self, reply="ok"):
        self.reply = reply

    def chat(self, messages, tools=None, on_chunk=None):
        return self.reply, []


class TodoTests(unittest.TestCase):
    def test_todo_reaches_prompt(self):
        session = AgentSession(make_config())
        session.add_todo("run the migration")
        self.assertIn("[TASK LIST]", session.messages[0]["content"])
        self.assertIn("[ ] run the migration", session.messages[0]["content"])

    def test_toggle_remove_clear(self):
        session = AgentSession(make_config())
        session.add_todo("a")
        session.add_todo("b")
        self.assertEqual(session.complete_todo(1), "a")
        self.assertTrue(session.todos[0]["done"])
        self.assertIn("[x] a", session.messages[0]["content"])
        self.assertEqual(session.remove_todo(2), "b")
        self.assertEqual(len(session.todos), 1)
        self.assertIsNone(session.complete_todo(9))
        session.clear_todos()
        self.assertNotIn("[TASK LIST]", session.messages[0]["content"])

    def test_todos_survive_compact_clear_and_resume(self):
        session = AgentSession(make_config())
        session.add_todo("keep me")
        for i in range(4):
            session.messages.append({"role": "user", "content": f"q{i}"})
            session.messages.append({"role": "assistant", "content": f"a{i}"})
        session.compact(keep_last_turns=1)
        self.assertIn("keep me", session.messages[0]["content"])

        session.reset()
        self.assertEqual(len(session.todos), 1)
        self.assertIn("keep me", session.messages[0]["content"])

        other = AgentSession(make_config())
        other.restore_from_dict(session._state() | {"messages": session.messages})
        self.assertEqual(other.todos, [{"text": "keep me", "done": False}])

    def test_build_system_prompt_todos_param(self):
        prompt = build_system_prompt(todos=[{"text": "x", "done": True}])
        self.assertIn("[x] x", prompt)


class NamedSnapshotTests(unittest.TestCase):
    def test_snapshot_and_restore(self):
        session = AgentSession(make_config())
        session.messages.append({"role": "user", "content": "first"})
        name = session.save_named_checkpoint("before-refactor")
        session.messages.append({"role": "user", "content": "second"})
        session.turns_count = 5

        self.assertTrue(session.restore_named_checkpoint("before-refactor"))
        self.assertEqual([m["content"] for m in session.messages[1:]], ["first"])
        self.assertEqual(session.turns_count, 0)
        self.assertFalse(session.restore_named_checkpoint("missing"))
        self.assertEqual(name, "before-refactor")

    def test_auto_label(self):
        session = AgentSession(make_config())
        self.assertEqual(session.save_named_checkpoint(""), "snapshot-1")


class UndoFileTests(unittest.TestCase):
    def test_undo_file_restores_without_touching_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "app.py"
            target.write_text("v1")
            session = AgentSession(make_config())
            session.create_checkpoint()
            session._snapshot_for_rewind(target)
            target.write_text("v2")
            session.messages.append({"role": "user", "content": "keep"})

            result = session.undo_file(str(target))
            self.assertIn("Dipulihkan", result)
            self.assertEqual(target.read_text(), "v1")
            self.assertEqual(session.messages[-1]["content"], "keep")

    def test_undo_file_without_snapshot(self):
        session = AgentSession(make_config())
        self.assertIsNone(session.undo_file("/tmp/definitely-not-snapshotted.txt"))


class BtwCounterTests(unittest.TestCase):
    def test_ephemeral_turn_does_not_inflate_stats(self):
        session = AgentSession(make_config())
        session.provider = _StubProvider("side answer")
        session.messages.append({"role": "user", "content": "real turn"})
        before = (session.turns_count, session.total_input_tokens, session.total_output_tokens)

        session.run_turn("side question", ephemeral=True, on_output=[].append)

        self.assertEqual(before[0], session.turns_count)
        self.assertEqual(before[1], session.total_input_tokens)
        self.assertEqual(before[2], session.total_output_tokens)
        self.assertNotIn("side question", [m.get("content") for m in session.messages])


class AliasTests(unittest.TestCase):
    def test_expand(self):
        cfg = make_config(aliases={"t": "/test pytest -x"})
        self.assertEqual(expand_alias(cfg, "/t"), "/test pytest -x")
        self.assertEqual(expand_alias(cfg, "/t tests/unit"), "/test pytest -x tests/unit")
        self.assertEqual(expand_alias(cfg, "/unknown"), "/unknown")
        self.assertEqual(expand_alias(cfg, "plain prompt"), "plain prompt")

    def test_alias_config_roundtrip(self):
        cfg = make_config(aliases={"q": "/quit"})
        self.assertEqual(Config(**cfg.model_dump()).aliases, {"q": "/quit"})


class DetectionTests(unittest.TestCase):
    def test_detect_cargo(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Cargo.toml").write_text("[package]\n")
            self.assertEqual(detect_test_command(Path(tmp)), "cargo test -q")

    def test_detect_go_and_lint(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "go.mod").write_text("module x\n")
            self.assertEqual(detect_test_command(Path(tmp)), "go test ./...")
            self.assertEqual(detect_lint_command(Path(tmp)), "gofmt -l .")

    def test_detect_npm_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"scripts": {"test": "vitest"}}')
            self.assertEqual(detect_test_command(Path(tmp)), "npm test --silent")

    def test_detect_npm_placeholder_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text(
                '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}'
            )
            self.assertIsNone(detect_test_command(Path(tmp)))

    def test_detect_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(detect_test_command(Path(tmp)))

    def test_npx_eslint_requires_local_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"scripts": {}}')
            with mock.patch(
                "onno_x.commands.shutil.which",
                side_effect=lambda name: "/usr/bin/npx" if name == "npx" else None,
            ):
                self.assertIsNone(detect_lint_command(Path(tmp)))

    def test_package_lint_script_is_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text(
                '{"scripts": {"lint": "eslint ."}}'
            )
            self.assertEqual(detect_lint_command(Path(tmp)), "npm run lint --silent")

    def test_local_eslint_binary_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"scripts": {}}')
            bin_dir = Path(tmp) / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "eslint").write_text("")
            with mock.patch(
                "onno_x.commands.shutil.which",
                side_effect=lambda name: "/usr/bin/npx" if name == "npx" else None,
            ):
                self.assertEqual(detect_lint_command(Path(tmp)), "npx --no-install eslint .")

    def test_missing_pyflakes_is_not_suggested(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "onno_x.commands.shutil.which",
                side_effect=lambda name: "/usr/bin/python" if name == "python" else None,
            ):
                self.assertIsNone(detect_lint_command(Path(tmp)))


class ReasoningTests(unittest.TestCase):
    def test_strips_multiple_blocks(self):
        raw = "a <think>one</think> b <thinking>two</thinking> c"
        self.assertEqual(strip_reasoning(raw).strip(), "a  b  c")

    def test_drops_unterminated_block(self):
        raw = "answer <think>still going"
        self.assertEqual(strip_reasoning(raw).strip(), "answer")


class SearchTests(unittest.TestCase):
    def _tree(self, tmp):
        (Path(tmp) / "src").mkdir()
        (Path(tmp) / "src" / "app.py").write_text("def handler():\n    return 'needle'\n")
        (Path(tmp) / ".git").mkdir()
        (Path(tmp) / ".git" / "config.py").write_text("needle in git dir\n")
        (Path(tmp) / "node_modules").mkdir()
        (Path(tmp) / "node_modules" / "x.py").write_text("needle in deps\n")

    def test_grep_finds_and_skips_vendor(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp)
            total, text = grep_repo("needle", Path(tmp))
            self.assertEqual(total, 1)
            self.assertIn("app.py", text)
            self.assertNotIn("node_modules", text)

    def test_find_skips_vendor(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp)
            total, text = find_files("app", Path(tmp))
            self.assertEqual(total, 1)
            self.assertIn("src/app.py", text)
            self.assertEqual(find_files("nope", Path(tmp)), (0, ""))


class GitCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run("git init -q && git config user.email a@b.c && git config user.email a@b.c",
                       shell=True, cwd=self.root, check=True, capture_output=True)
        subprocess.run("git config user.name tester", shell=True, cwd=self.root, check=True, capture_output=True)
        (self.root / "a.txt").write_text("one\n")
        subprocess.run("git add -A && git commit -qm 'feat: first commit'",
                       shell=True, cwd=self.root, check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_log(self):
        ok, text = git_log(5, self.root)
        self.assertTrue(ok)
        self.assertIn("feat: first commit", text)

    def test_stash_roundtrip(self):
        (self.root / "a.txt").write_text("two\n")
        ok, text = git_stash("push", "wip", self.root)
        self.assertTrue(ok, text)
        self.assertEqual((self.root / "a.txt").read_text(), "one\n")
        ok, text = git_stash("pop", "", self.root)
        self.assertTrue(ok, text)
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")

    def test_stash_outside_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, text = git_stash("push", "", Path(tmp))
            self.assertFalse(ok)
            self.assertIn("Bukan git", text)


class SessionTitleTests(unittest.TestCase):
    def test_title_wins_in_session_list(self):
        from onno_x.persistence import list_sessions, save_session

        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                save_session(
                    session_id="sess_titled",
                    messages=[{"role": "user", "content": "auto title from message"}],
                    model_name="m",
                    turns_count=0,
                    state={"title": "Custom title"},
                )
                row = next(s for s in list_sessions() if s["id"] == "sess_titled")
            finally:
                os.chdir(old)
            self.assertEqual(row["title"], "Custom title")


class TokenBreakdownTests(unittest.TestCase):
    def test_categories(self):
        messages = [
            {"role": "system", "content": "s" * 40},
            {"role": "user", "content": "u" * 40},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "t" * 40},
        ]
        rows = {r[0]: r[2] for r in token_breakdown(messages)}
        self.assertEqual(rows["system prompt"], 10)
        self.assertIn("tool call args", rows)
        self.assertIn("tool result", rows)
        self.assertGreaterEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
