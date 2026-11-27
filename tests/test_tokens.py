"""Token accounting tests.

Input used to be estimated from message `content` only (tool arguments were
free) and no "how full is the context" figure existed at all. These tests pin
estimate_tokens/estimate_output_tokens and how run_turn accumulates them.
"""

import unittest
from unittest import mock

from onno_x.config import Config, ModelSpec
from onno_x.session import AgentSession, estimate_output_tokens, estimate_tokens


class EstimateTests(unittest.TestCase):
    def test_tool_arguments_count_toward_input(self):
        plain = [{"role": "assistant", "content": "hi"}]
        with_calls = [{
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "t1", "function": {"name": "read", "arguments": "{\"path\": \"a\"}"}}],
        }]
        self.assertGreater(estimate_tokens(with_calls), estimate_tokens(plain))

    def test_estimates_never_return_zero(self):
        self.assertEqual(estimate_tokens([]), 1)
        self.assertEqual(estimate_output_tokens("", []), 0)

    def test_output_includes_tool_arguments(self):
        calls = [{"id": "t1", "function": {"name": "bash", "arguments": "ls -la"}}]
        self.assertGreater(estimate_output_tokens("", calls), 0)


class _ScriptedProvider:
    """Returns queued responses and records what each request carried."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.request_sizes = []

    def chat(self, messages, tools, on_chunk=None):
        self.request_sizes.append(estimate_tokens(messages))
        content, tool_calls = self.responses.pop(0)
        return content, tool_calls


class RunTurnTokenTests(unittest.TestCase):
    def _session(self, provider):
        cfg = Config(
            active_model="test",
            models={"test": ModelSpec(name="test", provider="openai", model_id="m")},
        )
        session = AgentSession(cfg)
        session.provider = provider
        return session

    def test_single_step_turn_records_context_and_output(self):
        provider = _ScriptedProvider([("hello there", [])])
        session = self._session(provider)

        with mock.patch("onno_x.session.save_session", lambda **kw: None):
            session.run_turn("hi", on_output=[].append)

        self.assertEqual(session.total_input_tokens, provider.request_sizes[0])
        self.assertEqual(session.last_input_tokens, provider.request_sizes[0])
        self.assertEqual(session.total_output_tokens, estimate_output_tokens("hello there", []))

    def test_tool_loop_accumulates_each_request(self):
        # Providers hand tool_calls back flat: id / name / arguments.
        calls = [{"id": "t1", "name": "read_file", "arguments": {"path": "a"}}]
        provider = _ScriptedProvider([("", calls), ("done", [])])
        session = self._session(provider)

        with mock.patch("onno_x.session.save_session", lambda **kw: None), \
             mock.patch("onno_x.session.execute_tool", lambda *a, **k: "tool output"):
            session.run_turn("find it", on_output=[].append)

        self.assertEqual(len(provider.request_sizes), 2)
        self.assertEqual(session.total_input_tokens, sum(provider.request_sizes))
        # The second request carries the whole history, so the context grows.
        self.assertGreater(session.last_input_tokens, provider.request_sizes[0])
        expected_out = estimate_output_tokens("", calls) + estimate_output_tokens("done", [])
        self.assertEqual(session.total_output_tokens, expected_out)


if __name__ == "__main__":
    unittest.main()
