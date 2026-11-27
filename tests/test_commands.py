"""Regression tests for the slash-command audit fixes.

Covers the commands that used to print success without doing anything:
/color, /goal, /advisor, /autocompact, /compact <instructions>, /rewind files,
plus the state that /resume now restores.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x.config import Config, ModelSpec, obsidian_url
from onno_x.session import AgentSession, build_system_prompt
from onno_x.ui import resolve_accent


def make_config(**kwargs):
    return Config(
        active_model="test",
        models={"test": ModelSpec(name="test", provider="openai", model_id="m")},
        **kwargs,
    )


class _StubProvider:
    def __init__(self, reply="RINGKASAN", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def chat(self, messages, tools=None, on_chunk=None):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.reply, []


class AccentTests(unittest.TestCase):
    def test_default_maps_to_cyan(self):
        self.assertEqual(resolve_accent("default"), "cyan")
        self.assertEqual(resolve_accent(None), "cyan")

    def test_prompt_style_uses_accent(self):
        from onno_x.main import build_prompt_style

        style = build_prompt_style("magenta")
        attrs = style.get_attrs_for_style_str("class:prompt.arrow")
        self.assertEqual(attrs.color.lower(), "ff00ff")  # rich renders magenta this way
        self.assertTrue(attrs.bold)

    def test_accent_persists_in_config(self):
        cfg = make_config(accent_color="green")
        self.assertEqual(Config(**cfg.model_dump()).accent_color, "green")


class GoalTests(unittest.TestCase):
    def test_goal_lands_in_system_prompt_and_clears(self):
        session = AgentSession(make_config())
        session.set_goal("ship the audit")
        self.assertIn("[ACTIVE GOAL]", session.messages[0]["content"])
        self.assertIn("ship the audit", session.messages[0]["content"])
        session.set_goal(None)
        self.assertNotIn("[ACTIVE GOAL]", session.messages[0]["content"])

    def test_build_system_prompt_accepts_goal(self):
        self.assertIn("goal text", build_system_prompt(goal="goal text"))


class RestoreTests(unittest.TestCase):
    def test_resume_restores_ui_state(self):
        session = AgentSession(make_config())
        session.restore_from_dict(
            {
                "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
                "permission_mode": "manual",
                "plan_mode": True,
                "extra_dirs": ["/tmp/extra"],
                "output_style": "concise",
                "fast_mode": True,
                "goal": "keep going",
            }
        )
        self.assertEqual(session.extra_dirs, ["/tmp/extra"])
        self.assertEqual(session.output_style, "concise")
        self.assertTrue(session.fast_mode)
        self.assertTrue(session.plan_mode)
        self.assertEqual(session.goal, "keep going")
        self.assertIn("keep going", session.messages[0]["content"])


class CompactTests(unittest.TestCase):
    def _seeded(self, turns=6):
        session = AgentSession(make_config())
        for i in range(turns):
            session.messages.append({"role": "user", "content": f"q{i}"})
            session.messages.append({"role": "assistant", "content": f"a{i}"})
        return session

    def test_compact_keeps_recent_turns(self):
        session = self._seeded()
        dropped = session.compact(keep_last_turns=2)
        self.assertGreater(dropped, 0)
        self.assertEqual(session.messages[-1]["content"], "a5")

    def test_compact_with_instructions_adds_summary(self):
        session = self._seeded()
        session.provider = _StubProvider("model summary")
        session.compact(keep_last_turns=2, instructions="keep the API keys discussion")
        bodies = " ".join(str(m.get("content")) for m in session.messages)
        self.assertIn("model summary", bodies)
        self.assertIn("keep the API keys discussion", bodies)

    def test_compact_summary_failure_falls_back_to_trim(self):
        session = self._seeded()
        session.provider = _StubProvider(error=RuntimeError("boom"))
        dropped = session.compact(keep_last_turns=2, instructions="focus")
        self.assertGreater(dropped, 0)
        self.assertNotIn("model summary", " ".join(str(m.get("content")) for m in session.messages))


class AutocompactTests(unittest.TestCase):
    def _session(self, threshold):
        session = AgentSession(make_config(autocompact_threshold=threshold))
        session.messages.append({"role": "user", "content": "hello"})
        session.messages.append({"role": "assistant", "content": "hi"})
        for i in range(6):
            session.messages.append({"role": "user", "content": "x" * 1500 + f" {i}"})
            session.messages.append({"role": "assistant", "content": "y" * 1500})
        return session

    def test_zero_disables_trim(self):
        session = self._session(0)
        before = len(session.messages)
        session._auto_trim_context_if_needed()
        self.assertEqual(len(session.messages), before)

    def test_explicit_threshold_trims(self):
        session = self._session(10)
        before = len(session.messages)
        session._auto_trim_context_if_needed()
        self.assertLess(len(session.messages), before)

    def test_auto_mode_uses_model_capacity(self):
        session = self._session(None)
        before = len(session.messages)
        session._auto_trim_context_if_needed()
        # Small models get a 3200-token threshold; this context is well past it.
        self.assertLess(len(session.messages), before)


class RewindFileTests(unittest.TestCase):
    def test_rewind_restores_edited_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "code.py"
            target.write_text("original\n")
            session = AgentSession(make_config())
            session.create_checkpoint()
            session._snapshot_for_rewind(target)
            target.write_text("broken\n")
            result = session.rewind_checkpoint()
            self.assertTrue(result["reverted"])
            self.assertEqual(target.read_text(), "original\n")
            self.assertTrue(result["files_restored"])

    def test_rewind_deletes_created_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "new.py"
            session = AgentSession(make_config())
            session.create_checkpoint()
            session._snapshot_for_rewind(target)
            target.write_text("created\n")
            session.rewind_checkpoint()
            self.assertFalse(target.exists())

    def test_snapshot_keeps_first_version_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("v1")
            session = AgentSession(make_config())
            session.create_checkpoint()
            session._snapshot_for_rewind(target)
            target.write_text("v2")
            session._snapshot_for_rewind(target)
            session.rewind_checkpoint()
            self.assertEqual(target.read_text(), "v1")


class AdvisorTests(unittest.TestCase):
    def test_advisor_returns_critique(self):
        session = AgentSession(make_config())
        session.config.models["adv"] = ModelSpec(name="adv", provider="openai", model_id="a")
        session.advisor_model = "adv"
        stub = _StubProvider("risky edge case on empty input")
        with mock.patch("onno_x.session.get_provider", lambda spec: stub):
            text = session._run_advisor("my answer")
        self.assertIn("risky edge case", text)
        self.assertEqual(len(stub.calls), 1)

    def test_advisor_failure_is_swallowed(self):
        session = AgentSession(make_config())
        session.config.models["adv"] = ModelSpec(name="adv", provider="openai", model_id="a")
        session.advisor_model = "adv"
        with mock.patch("onno_x.session.get_provider", lambda spec: _StubProvider(error=RuntimeError("x"))):
            self.assertIsNone(session._run_advisor("answer"))

    def test_advisor_disabled_does_nothing(self):
        session = AgentSession(make_config())
        self.assertIsNone(session._run_advisor("answer"))

    def test_run_turn_consults_advisor(self):
        session = AgentSession(make_config())
        session.config.models["adv"] = ModelSpec(name="adv", provider="openai", model_id="a")
        session.advisor_model = "adv"
        session.provider = _StubProvider("main answer")
        advisor = _StubProvider("watch the empty case")

        with mock.patch("onno_x.session.get_provider", lambda spec: advisor), \
             mock.patch("onno_x.session.save_session", lambda **kw: None):
            session.run_turn("hello", on_output=[].append)

        self.assertEqual(len(advisor.calls), 1)


class OutputStyleTests(unittest.TestCase):
    def test_style_reaches_system_prompt(self):
        session = AgentSession(make_config())
        self.assertNotIn("[OUTPUT STYLE", session.messages[0]["content"])
        session.set_output_style("concise")
        self.assertIn("[OUTPUT STYLE: concise]", session.messages[0]["content"])
        session.set_output_style("default")
        self.assertNotIn("[OUTPUT STYLE", session.messages[0]["content"])

    def test_clear_keeps_goal_and_style(self):
        session = AgentSession(make_config())
        session.set_goal("do not lose this")
        session.set_output_style("verbose")
        session.reset()
        self.assertIn("do not lose this", session.messages[0]["content"])
        self.assertIn("[OUTPUT STYLE: verbose]", session.messages[0]["content"])


class MemoryFileTests(unittest.TestCase):
    def test_long_onnO_md_is_not_cut_at_1kb(self):
        from onno_x.session import build_system_prompt

        with tempfile.TemporaryDirectory() as tmp:
            tail = "INSTRUKSI-TERAKHIR-DARI-MEMORY"
            (Path(tmp) / "ONNO.md").write_text("x" * 3000 + "\n" + tail + "\n", encoding="utf-8")
            old = os.getcwd()
            os.chdir(tmp)
            try:
                prompt = build_system_prompt()
            finally:
                os.chdir(old)
            self.assertIn(tail, prompt)


class AutosaveStateTests(unittest.TestCase):
    def test_autosave_keeps_ui_state(self):
        session = AgentSession(make_config())
        session.provider = _StubProvider("done")
        session.set_goal("persist me")
        session.output_style = "concise"
        captured = {}

        def fake_save(**kwargs):
            captured.update(kwargs)
            return Path("/tmp/fake.json")

        with mock.patch("onno_x.session.save_session", fake_save):
            session.run_turn("hello", on_output=[].append)

        self.assertEqual(captured["state"]["goal"], "persist me")
        self.assertEqual(captured["state"]["output_style"], "concise")


class SpecPersistenceTests(unittest.TestCase):
    def test_fast_mode_and_effort_save_config(self):
        session = AgentSession(make_config())
        with mock.patch("onno_x.session.save_config") as saver:
            session.toggle_fast_mode()
            self.assertTrue(saver.called)
        with mock.patch("onno_x.session.save_config") as saver:
            session.set_effort("high")
            self.assertTrue(saver.called)
        self.assertEqual(session.spec.temperature, 0.5)


class SessionIdTests(unittest.TestCase):
    def test_saved_id_is_sanitized(self):
        from onno_x.persistence import load_session, save_session

        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                path = save_session(
                    session_id="  sess_trim  ",
                    messages=[{"role": "user", "content": "hi"}],
                    model_name="m",
                    turns_count=1,
                )
                data = load_session(path.stem)
            finally:
                os.chdir(old)
            self.assertIsNotNone(data)
            self.assertEqual(data["session_id"], path.stem)
            self.assertEqual(data["session_id"], "sess_trim")


class EndpointTests(unittest.TestCase):
    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"ONNO_OBSIDIAN_URL": "http://127.0.0.1:9000/"}):
            self.assertEqual(obsidian_url(), "http://127.0.0.1:9000")


class MenuTests(unittest.TestCase):
    def test_aliases_are_documented(self):
        from onno_x.main import SLASH_COMMANDS

        advertised = {cmd for cmd, _ in SLASH_COMMANDS}
        for alias in ("/accept-all", "/auto-resume", "/bell", "/limit", "/memo", "/save-session", "/yolo"):
            self.assertIn(alias, advertised)

    def test_every_advertised_command_has_a_handler(self):
        import re

        from onno_x.main import SLASH_COMMANDS

        source = Path(__file__).resolve().parent.parent.joinpath("onno_x/main.py").read_text(encoding="utf-8")
        handled = set(re.findall(r'base_cmd\s*==\s*"([^"]+)"', source))
        for group in re.findall(r"base_cmd\s+in\s+\(([^)]*)\)", source):
            handled |= set(re.findall(r'"(\/[^"]+)"', group))
        handled |= set(re.findall(r'base_cmd\.startswith\(\s*"([^"]+)"', source))
        missing = [cmd for cmd, _ in SLASH_COMMANDS if cmd not in handled]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
