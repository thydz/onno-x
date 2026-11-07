import os
from typing import Any, Dict, List, Tuple
import httpx
from onno_x.providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_chunk: Any = None,
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

        system_prompt = "You are onno-x, an expert autonomous coding assistant. Solve tasks directly using tools."
        filtered_messages = []
        for m in messages:
            role = m["role"]
            if role == "system":
                system_prompt = m["content"]
                continue
            if role == "tool":
                filtered_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.get("tool_call_id", "tool_use_default"),
                            "content": m.get("content", ""),
                        }
                    ],
                })
            elif role == "assistant" and m.get("tool_calls"):
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            import json
                            args = json.loads(args)
                        except Exception:
                            args = {"raw": args}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": fn.get("name"),
                        "input": args,
                    })
                filtered_messages.append({"role": "assistant", "content": blocks})
            else:
                filtered_messages.append({"role": role, "content": m.get("content", "")})

        payload: Dict[str, Any] = {
            "model": self.spec.model_id,
            "system": system_prompt,
            "messages": filtered_messages,
            "max_tokens": min(self.spec.max_tokens, 4096),
            "temperature": self.spec.temperature,
            "stream": bool(on_chunk),
        }
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        timeout_val = getattr(self.spec, "timeout", 300.0) or 300.0

        if on_chunk:
            text_parts = []
            tool_calls_map: Dict[int, Dict[str, Any]] = {}
            with httpx.Client(timeout=timeout_val) as client:
                with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
                    if resp.status_code >= 400:
                        resp.read()
                        raise RuntimeError(f"Anthropic streaming error [{resp.status_code}]: {resp.text}")
                    import json
                    for line in resp.iter_lines():
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

                            if ev_type == "content_block_start":
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

            return "".join(text_parts), tool_calls
