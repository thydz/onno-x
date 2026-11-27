import json
from typing import Any, Dict, List, Tuple
import httpx
from onno_x.providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        on_chunk: Any = None,
        cancel_event: Any = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        base_url = (self.spec.base_url or "http://localhost:11434").rstrip("/")

        # Convert tool format for Ollama chat API
        ollama_tools = []
        for t in tools:
            ollama_tools.append(t)

        payload = {
            "model": self.spec.model_id,
            "messages": messages,
            "stream": bool(on_chunk),
            "options": {
                "temperature": self.spec.temperature,
            },
        }
        if ollama_tools:
            payload["tools"] = ollama_tools

        timeout_val = getattr(self.spec, "timeout", 180.0) or 180.0

        if on_chunk:
            content_parts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []
            done_reason = [None]
            with httpx.Client(timeout=timeout_val) as client:
                with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
                    if resp.status_code >= 400:
                        resp.read()
                        raise RuntimeError(f"Ollama streaming error [{resp.status_code}]: {resp.text}")
                    for line in resp.iter_lines():
                        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                            raise InterruptedError("Turn cancelled by user")
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            if chunk.get("done_reason"):
                                done_reason[0] = chunk["done_reason"]
                            msg = chunk.get("message", {})
                            token = msg.get("content", "")
                            if token:
                                content_parts.append(token)
                                on_chunk(token)
                            for call in msg.get("tool_calls", []):
                                fn = call.get("function", {})
                                tool_calls.append({
                                    # Unique id per call; don't reset idx per
                                    # chunk or reuse ids across streamed calls.
                                    "id": call.get("id") or f"call_ollama_{len(tool_calls)}",
                                    "name": fn.get("name"),
                                    "arguments": fn.get("arguments", {}),
                                })
                        except InterruptedError:
                            # User cancelled the turn: never swallow this signal.
                            raise
                        except Exception:
                            continue
            self.last_truncated = done_reason[0] == "length"
            return "".join(content_parts), tool_calls

        with httpx.Client(timeout=timeout_val) as client:
            resp = client.post(f"{base_url}/api/chat", json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Ollama error [{resp.status_code}]: {resp.text}")

            data = resp.json()
            msg = data.get("message", {})
            content = msg.get("content", "")
            raw_calls = msg.get("tool_calls", [])

            tool_calls = []
            for idx, call in enumerate(raw_calls):
                fn = call.get("function", {})
                tool_calls.append({
                    "id": call.get("id") or f"call_ollama_{idx}",
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments", {}),
                })

            self.last_truncated = data.get("done_reason") == "length"
            return content, tool_calls
