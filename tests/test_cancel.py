"""Regression tests for turn cancellation.

ESC in the TUI and the Stop button in the web UI set session.cancel_requested;
session.on_chunk then raises InterruptedError. Providers used to run on_chunk
inside a bare `try/except Exception: continue`, which swallowed the cancel and
let the whole stream finish. These tests pin the fixed behaviour.
"""

import json
import unittest
from unittest import mock

import httpx

from onno_x.config import Config, ModelSpec
from onno_x.providers.anthropic import AnthropicProvider
from onno_x.providers.ollama import OllamaProvider
from onno_x.providers.openai import OpenAIProvider
from onno_x.session import AgentSession


class _FakeResponse:
    def __init__(self, lines, status=200):
        self._lines = lines
        self.status_code = status
        self.text = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b""

    def iter_lines(self):
        for line in self._lines:
            yield line


def _fake_client_class(lines):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, *args, **kwargs):
            return _FakeResponse(lines)

        def post(self, *args, **kwargs):
            return _FakeResponse([])

    return _FakeClient


def _cancel_on_second_chunk(seen):
    def on_chunk(token):
        seen.append(token)
        if len(seen) == 2:
            raise InterruptedError("cancelled by user")

    return on_chunk


class ProviderCancelTests(unittest.TestCase):
    def _spec(self, provider):
        return ModelSpec(
            name="test", provider=provider, model_id="test-model", api_key="k"
        )

    def _assert_cancel_propagates(self, provider_obj, lines):
        seen = []
        with mock.patch.object(httpx, "Client", _fake_client_class(lines)):
            with self.assertRaises(InterruptedError):
                provider_obj.chat(
                    [{"role": "user", "content": "hi"}], [], on_chunk=_cancel_on_second_chunk(seen)
                )
        self.assertEqual(seen, ["tok0 ", "tok1 "])

    def test_openai_stream_cancel_propagates(self):
        lines = [
            "data: " + json.dumps({"choices": [{"delta": {"content": f"tok{i} "}}]})
            for i in range(5)
        ] + ["data: [DONE]"]
        self._assert_cancel_propagates(OpenAIProvider(self._spec("openai")), lines)

    def test_anthropic_stream_cancel_propagates(self):
        lines = [
            "data: "
            + json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": f"tok{i} "},
                }
            )
            for i in range(5)
        ]
        self._assert_cancel_propagates(AnthropicProvider(self._spec("anthropic")), lines)

    def test_ollama_stream_cancel_propagates(self):
        lines = [
            json.dumps({"message": {"content": f"tok{i} "}}) for i in range(5)
        ]
        self._assert_cancel_propagates(OllamaProvider(self._spec("ollama")), lines)


class _CancellingProvider:
    """Sets the cancel flag mid-stream, like the UI would."""

    def __init__(self, session):
        self.session = session

    def chat(self, messages, tools, on_chunk=None):
        for i in range(5):
            if i == 3:
                self.session.cancel_requested.set()
            on_chunk(f"t{i} ")
        return "should never be returned", []


class _ToolCallThenCancelProvider:
    """Returns two tool calls and flips the cancel flag before they run."""

    def __init__(self, session):
        self.session = session

    def chat(self, messages, tools, on_chunk=None):
        self.session.cancel_requested.set()
        return "", [
            {"id": "t1", "name": "read_file", "arguments": {"path": "a.py"}},
            {"id": "t2", "name": "list_dir", "arguments": {}},
        ]


class _StreamOnlyProvider:
    """Streams chunks through on_chunk, like a real provider."""

    def chat(self, messages, tools, on_chunk=None):
        for token in ("halo ", "dunia"):
            if on_chunk:
                on_chunk(token)
        return "halo dunia", []


class SessionCancelTests(unittest.TestCase):
    def _session(self):
        cfg = Config(
            active_model="test",
            models={"test": ModelSpec(name="test", provider="openai", model_id="m")},
        )
        return AgentSession(cfg)

    def test_cancel_mid_tool_loop_closes_dangling_tool_calls(self):
        session = self._session()
        session.provider = _ToolCallThenCancelProvider(session)

        with mock.patch("onno_x.session.save_session", lambda **kwargs: None):
            session.run_turn("hello", on_output=lambda _r: None)

        # The assistant message carries two tool_calls; both need a reply or the
        # next request is rejected by OpenAI/Anthropic.
        tool_msgs = [m for m in session.messages if m.get("role") == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["t1", "t2"])

    def test_output_without_token_callback_still_renders_text(self):
        session = self._session()
        session.provider = _StreamOnlyProvider()
        rendered = []

        with mock.patch("onno_x.session.save_session", lambda **kwargs: None):
            session.run_turn("hello", on_output=rendered.append)

        joined = " ".join(getattr(r, "markup", str(r)) for r in rendered)
        self.assertIn("halo dunia", joined)

    def test_run_turn_stops_without_provider_error(self):
        session = self._session()
        session.provider = _CancellingProvider(session)
        tokens = []
        rendered = []

        with mock.patch("onno_x.session.save_session", lambda **kwargs: None):
            result = session.run_turn(
                "hello",
                on_output=rendered.append,
                on_token=tokens.append,
            )

        # Cancel is set before the 4th chunk, so exactly 3 tokens are delivered.
        self.assertEqual(tokens, ["t0 ", "t1 ", "t2 "])
        self.assertEqual(result, "")
        self.assertEqual(session.turns_count, 1)


if __name__ == "__main__":
    unittest.main()
