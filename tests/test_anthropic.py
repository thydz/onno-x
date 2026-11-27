import unittest

from onno_x.providers.anthropic import to_anthropic_messages


def _tool_call(call_id, name, arguments):
    return {"id": call_id, "function": {"name": name, "arguments": arguments}}


class AnthropicMessageTests(unittest.TestCase):
    def test_consecutive_tool_results_share_one_user_message(self):
        _, out = to_anthropic_messages([
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    _tool_call("t1", "read", '{"path": "a"}'),
                    _tool_call("t2", "grep", {"q": "x"}),
                    _tool_call("t3", "bash", "not json"),
                ],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "A"},
            {"role": "tool", "tool_call_id": "t2", "content": "B"},
            {"role": "tool", "tool_call_id": "t3", "content": "C"},
            {"role": "assistant", "content": "done"},
        ])

        # Alternation must hold: user, assistant, user, assistant.
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user", "assistant"])
        self.assertEqual([b["type"] for b in out[1]["content"]], ["tool_use"] * 3)
        self.assertEqual(out[1]["content"][0]["input"], {"path": "a"})
        self.assertEqual(out[1]["content"][1]["input"], {"q": "x"})
        self.assertEqual(out[1]["content"][2]["input"], {"raw": "not json"})

        results = out[2]["content"]
        self.assertEqual(len(results), 3)
        self.assertTrue(all(b["type"] == "tool_result" for b in results))
        self.assertEqual([b["tool_use_id"] for b in results], ["t1", "t2", "t3"])

    def test_system_prompt_is_extracted_not_left_in_messages(self):
        system, out = to_anthropic_messages([
            {"role": "system", "content": "CUSTOM SYS"},
            {"role": "user", "content": "hi"},
        ])
        self.assertEqual(system, "CUSTOM SYS")
        self.assertEqual(out, [{"role": "user", "content": "hi"}])

    def test_user_message_after_tool_results_joins_the_same_user_turn(self):
        # Anthropic rejects two user messages in a row, so the follow-up prompt
        # rides along as a text block after the tool_result blocks.
        _, out = to_anthropic_messages([
            {"role": "assistant", "content": "", "tool_calls": [_tool_call("t1", "read", "{}")]},
            {"role": "tool", "tool_call_id": "t1", "content": "A"},
            {"role": "user", "content": "next"},
        ])
        self.assertEqual([m["role"] for m in out], ["assistant", "user"])
        blocks = out[1]["content"]
        self.assertEqual(blocks[0]["type"], "tool_result")
        self.assertEqual(blocks[0]["tool_use_id"], "t1")
        self.assertEqual(blocks[-1], {"type": "text", "text": "next"})

    def test_consecutive_user_messages_are_merged(self):
        _, out = to_anthropic_messages([
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ])
        self.assertEqual(out, [{"role": "user", "content": "first\n\nsecond"}])


if __name__ == "__main__":
    unittest.main()
