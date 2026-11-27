import json
import os
from typing import Any, Dict, List, Tuple
import httpx
from onno_x.providers.base import BaseProvider


DEFAULT_SYSTEM_PROMPT = (
    "You are onno-x, an expert autonomous coding assistant. "
    "Always communicate in Bahasa Indonesia while keeping code and technical terms accurate. "
    "Solve tasks directly using tools."
)


def to_anthropic_messages(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Translate OpenAI-style history into Anthropic's system/messages shape.

    Anthropic requires every `tool_result` for an assistant turn to arrive inside
    a *single* user message, and rejects two user messages in a row. A tool loop
    emits one `tool` message per call, so consecutive results are folded into the
    user message that already holds `tool_result` blocks.
    """
    system_prompt = DEFAULT_SYSTEM_PROMPT
    filtered: List[Dict[str, Any]] = []

    for m in messages:
        role = m.get("role")
        if role == "system":
            system_prompt = m.get("content") or system_prompt
            continue

        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id") or "tool_use_default",
                "content": m.get("content", ""),
            }
            prev = filtered[-1] if filtered else None
            if (
                isinstance(prev, dict)
                and prev.get("role") == "user"
                and isinstance(prev.get("content"), list)
                and all(b.get("type") == "tool_result" for b in prev["content"])
            ):
                prev["content"].append(block)
            else:
                filtered.append({"role": "user", "content": [block]})
            continue

        if role == "assistant" and m.get("tool_calls"):
            blocks: List[Dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw": args}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "input": args,
                })
            filtered.append({"role": "assistant", "content": blocks})
            continue

        if role == "user":
            content = m.get("content", "")
            prev = filtered[-1] if filtered else None
            # Anthropic rejects two user messages in a row. A tool turn followed
            # by a fresh prompt (or a resumed history) hits that, so fold them.
            if isinstance(prev, dict) and prev.get("role") == "user":
                prev_content = prev.get("content")
                if isinstance(prev_content, list):
                    if content:
                        prev_content.append({"type": "text", "text": str(content)})
                else:
                    joined = [str(prev_content or ""), str(content or "")]
                    prev["content"] = "\n\n".join(part for part in joined if part)
                continue

        filtered.append({"role": role, "content": m.get("content", "")})

    return system_prompt, filtered


class AnthropicProvider(BaseProvider):
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_chunk: Any = None,
        cancel_event: Any = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        api_key = self.spec.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in spec or environment.")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        anthropic_tools = []
        for t in tools:
            fn = t.get("function", {})
            anthropic_tools.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })

        system_prompt, filtered_messages = to_anthropic_messages(messages)

        payload: Dict[str, Any] = {
            "model": self.spec.model_id,
            "system": system_prompt,
            "messages": filtered_messages,
            "max_tokens": max(1, min(self.spec.max_tokens or 1, 4096)),
            "temperature": self.spec.temperature,
            "stream": bool(on_chunk),
        }
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        timeout_val = getattr(self.spec, "timeout", 300.0) or 300.0

        if on_chunk:
            text_parts = []
            tool_calls_map: Dict[int, Dict[str, Any]] = {}
            stop_reason = [None]
            with httpx.Client(timeout=timeout_val) as client:
                with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
                    if resp.status_code >= 400:
                        resp.read()
                        raise RuntimeError(f"Anthropic streaming error [{resp.status_code}]: {resp.text}")
                    for line in resp.iter_lines():
                        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                            raise InterruptedError("Turn cancelled by user")
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            event_data = json.loads(data_str)
                            ev_type = event_data.get("type")
                            idx = event_data.get("index", 0)

                            if ev_type == "message_delta":
                                stop = (event_data.get("delta") or {}).get("stop_reason")
                                if stop:
                                    stop_reason[0] = stop
                            elif ev_type == "content_block_start":
                                block = event_data.get("content_block", {})
                                if block.get("type") == "tool_use":
                                    tool_calls_map[idx] = {
                                        "id": block.get("id"),
                                        "name": block.get("name"),
                                        "input_json": "",
                                    }
                            elif ev_type == "content_block_delta":
                                delta = event_data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    token = delta.get("text", "")
                                    text_parts.append(token)
                                    on_chunk(token)
                                elif delta.get("type") == "input_json_delta":
                                    if idx in tool_calls_map:
                                        tool_calls_map[idx]["input_json"] += delta.get("partial_json", "")
                        except InterruptedError:
                            # User cancelled the turn: never swallow this signal.
                            raise
                        except Exception:
                            continue

            tool_calls = []
            for tc in tool_calls_map.values():
                args = {}
                try:
                    args = json.loads(tc["input_json"]) if tc["input_json"] else {}
                except Exception:
                    args = {"raw": tc["input_json"]}
                tool_calls.append({"id": tc["id"], "name": tc["name"], "arguments": args})

            self.last_truncated = stop_reason[0] == "max_tokens"
            return "".join(text_parts), tool_calls

        with httpx.Client(timeout=timeout_val) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Anthropic error [{resp.status_code}]: {resp.text}")

            data = resp.json()
            content_blocks = data.get("content", [])
            text_parts = []
            tool_calls = []

            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": block.get("input", {}),
                    })

            self.last_truncated = data.get("stop_reason") == "max_tokens"
            return "".join(text_parts), tool_calls
