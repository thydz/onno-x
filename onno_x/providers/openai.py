import json
import os
import re
from typing import Any, Dict, List, Tuple
import httpx
from onno_x.providers.base import BaseProvider


def extract_fallback_tool_calls(content: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract tool calls if the model outputted raw JSON instead of using structured tool_calls."""
    tool_calls = []
    clean_content = content.strip()

    # Pattern 1: <tool_call>JSON</tool_call>
    tool_call_tags = re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", clean_content, flags=re.DOTALL)
    for tag_json in tool_call_tags:
        try:
            parsed = json.loads(tag_json)
            name = parsed.get("name")
            args = parsed.get("arguments") or parsed.get("parameters") or {}
            if name:
                tool_calls.append({"id": f"call_tag_{len(tool_calls)}", "name": name, "arguments": args})
                clean_content = clean_content.replace(f"<tool_call>{tag_json}</tool_call>", "").strip()
        except Exception:
            pass

    if tool_calls:
        return clean_content, tool_calls

    # Pattern 2: Markdown code block ```json {"name": ...} ```
    code_blocks = re.findall(r"```(?:json)?\s*(\{[^{}]*\"name\"[^{}]*\})\s*```", clean_content, flags=re.DOTALL)
    for cb_json in code_blocks:
        try:
            parsed = json.loads(cb_json)
            name = parsed.get("name")
            args = parsed.get("arguments") or parsed.get("parameters") or {}
            if name:
                tool_calls.append({"id": f"call_cb_{len(tool_calls)}", "name": name, "arguments": args})
                clean_content = clean_content.replace(cb_json, "").replace("```json", "").replace("```", "").strip()
        except Exception:
            pass

    if tool_calls:
        return clean_content, tool_calls

    # Pattern 3: Standalone raw JSON object {"name": "...", "arguments": ...}
    stripped = clean_content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            name = parsed.get("name")
            args = parsed.get("arguments")
            if args is None:
                args = parsed.get("parameters", {})
            if name:
                tool_calls.append({"id": "call_raw_0", "name": name, "arguments": args})
                return "", tool_calls
        except Exception:
            pass

    # Pattern 4: Embedded JSON anywhere in text
    embedded_matches = re.findall(r'(\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"(?:arguments|parameters)"\s*:\s*\{.*?\}\s*\})', clean_content, flags=re.DOTALL)
    for match_str in embedded_matches:
        try:
            parsed = json.loads(match_str)
            name = parsed.get("name")
            args = parsed.get("arguments") or parsed.get("parameters") or {}
            if name:
                tool_calls.append({"id": f"call_embed_{len(tool_calls)}", "name": name, "arguments": args})
                clean_content = clean_content.replace(match_str, "").strip()
        except Exception:
            pass

    return clean_content, tool_calls


def parse_sse_stream(text: str) -> Tuple[str, List[Dict[str, Any]], bool]:
    """Parse Server-Sent Events (SSE) stream if proxy forces streaming chunks.

    Returns (text, tool_calls, truncated). `truncated` is True when any choice
    reports finish_reason == "length", i.e. output was cut at max_tokens.
    """
    content_parts: List[str] = []
    tool_calls_map: Dict[int, Dict[str, Any]] = {}
    truncated = False

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if data_str == "[DONE]" or not data_str:
            continue
        try:
            chunk = json.loads(data_str)
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if choices[0].get("finish_reason") == "length":
                truncated = True

            # Append content chunks
            # Reasoning is deliberately not part of the final answer.
            if delta.get("content"):
                content_parts.append(delta["content"])

            # Accumulate streaming tool calls
            for raw_tc in delta.get("tool_calls") or []:
                idx = raw_tc.get("index", 0)
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {
                        "id": raw_tc.get("id") or f"call_{idx}",
                        "name": "",
                        "arguments": "",
                    }
                fn = raw_tc.get("function") or {}
                if fn.get("name"):
                    tool_calls_map[idx]["name"] += fn["name"]
                if fn.get("arguments"):
                    tool_calls_map[idx]["arguments"] += fn["arguments"]
        except Exception:
            continue

    tool_calls = []
    for tc in tool_calls_map.values():
        args = {}
        try:
            args = json.loads(tc["arguments"])
        except Exception:
            args = {"raw": tc["arguments"]}
        tool_calls.append({
            "id": tc["id"],
            "name": tc["name"],
            "arguments": args,
        })

    final_text = "".join(content_parts)
    return final_text, tool_calls, truncated


class OpenAIProvider(BaseProvider):
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_chunk: Any = None,
        cancel_event: Any = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        base_url = (self.spec.base_url or "https://api.openai.com/v1").rstrip("/")
        if not base_url.endswith("/v1") and not base_url.endswith("/chat/completions"):
            endpoint = f"{base_url}/v1/chat/completions"
        elif base_url.endswith("/chat/completions"):
            endpoint = base_url
        else:
            endpoint = f"{base_url}/chat/completions"

        api_key = self.spec.api_key or os.getenv("OPENAI_API_KEY") or "EMPTY"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Cap max_tokens to a realistic response limit if set astronomically high
        max_tok = max(1, self.spec.max_tokens or 1)
        if max_tok > 8192:
            max_tok = 4096

        payload: Dict[str, Any] = {
            "model": self.spec.model_id,
            "messages": messages,
            "temperature": self.spec.temperature,
            "max_tokens": max_tok,
            "stream": bool(on_chunk),
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        timeout_val = getattr(self.spec, "timeout", 300.0) or 300.0

        # Handle real-time streaming if on_chunk callback provided
        if on_chunk:
            content_parts: List[str] = []
            tool_calls_map: Dict[int, Dict[str, Any]] = {}
            in_reasoning = [False]
            finish_reason = [None]
            with httpx.Client(timeout=timeout_val) as client:
                with client.stream("POST", endpoint, headers=headers, json=payload) as resp:
                    if resp.status_code >= 400:
                        resp.read()
                        raise RuntimeError(f"OpenAI streaming error [{resp.status_code}]: {resp.text}")
                    for line in resp.iter_lines():
                        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                            raise InterruptedError("Turn cancelled by user")
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]" or not data_str:
                            continue
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            reason = choices[0].get("finish_reason")
                            if reason:
                                finish_reason[0] = reason
                            reason_tok = delta.get("reasoning_content") or delta.get("thought")
                            if reason_tok and on_chunk:
                                if not in_reasoning[0]:
                                    in_reasoning[0] = True
                                    on_chunk("<think>")
                                on_chunk(reason_tok)
                            if delta.get("content"):
                                if in_reasoning[0]:
                                    in_reasoning[0] = False
                                    if on_chunk:
                                        on_chunk("</think>")
                                token = delta["content"]
                                content_parts.append(token)
                                on_chunk(token)
                            for raw_tc in delta.get("tool_calls") or []:
                                idx = raw_tc.get("index", 0)
                                if idx not in tool_calls_map:
                                    tool_calls_map[idx] = {
                                        "id": raw_tc.get("id") or f"call_{idx}",
                                        "name": "",
                                        "arguments": "",
                                    }
                                fn = raw_tc.get("function") or {}
                                if fn.get("name"):
                                    tool_calls_map[idx]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    tool_calls_map[idx]["arguments"] += fn["arguments"]
                        except InterruptedError:
                            # User cancelled the turn: never swallow this signal.
                            raise
                        except Exception:
                            continue

                    if in_reasoning[0] and on_chunk:
                        on_chunk("</think>")

            full_content = "".join(content_parts)
            tool_calls = []
            for tc in tool_calls_map.values():
                args = {}
                try:
                    args = json.loads(tc["arguments"])
                except Exception:
                    args = {"raw": tc["arguments"]}
                tool_calls.append({"id": tc["id"], "name": tc["name"], "arguments": args})

            if not tool_calls and full_content:
                full_content, extracted = extract_fallback_tool_calls(full_content)
                if extracted:
                    tool_calls = extracted

            # 'length' means the model hit max_tokens mid-answer. The caller
            # continues the turn instead of committing the fragment.
            self.last_truncated = finish_reason[0] == "length"
            return full_content, tool_calls

        # Fallback to standard non-streaming POST
        with httpx.Client(timeout=timeout_val) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenAI error [{resp.status_code}]: {resp.text}")

            resp_text = resp.text.strip()

            # Handle server forcing Server-Sent Events (SSE) streaming format
            if resp_text.startswith("data:"):
                content, tool_calls, truncated = parse_sse_stream(resp_text)
                if not tool_calls and content:
                    content, extracted = extract_fallback_tool_calls(content)
                    if extracted:
                        tool_calls = extracted
                self.last_truncated = truncated
                return content, tool_calls

            try:
                data = resp.json()
            except Exception:
                raise RuntimeError(f"Invalid JSON from [{endpoint}] (HTTP {resp.status_code}): {resp.text[:300]}")

            choice = data["choices"][0]["message"]
            content = choice.get("content") or ""
            tool_calls = []

            for raw_call in choice.get("tool_calls") or []:
                fn = raw_call.get("function", {})
                args = {}
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {"raw": fn.get("arguments", "")}

                tool_calls.append({
                    "id": raw_call.get("id", "call_default"),
                    "name": fn.get("name"),
                    "arguments": args,
                })

            # Fallback for local models that output tool call JSON as raw content text
            if not tool_calls and content:
                content, extracted = extract_fallback_tool_calls(content)
                if extracted:
                    tool_calls = extracted

            self.last_truncated = data["choices"][0].get("finish_reason") == "length"
            return content, tool_calls
