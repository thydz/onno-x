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
            with httpx.Client(timeout=timeout_val) as client:
                with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
                    if resp.status_code >= 400:
                        resp.read()
                        raise RuntimeError(f"Ollama streaming error [{resp.status_code}]: {resp.text}")
                    for line in resp.iter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            msg = chunk.get("message", {})
                            token = msg.get("content", "")
                            if token:
                                content_parts.append(token)
                                on_chunk(token)
                            for idx, call in enumerate(msg.get("tool_calls", [])):
                                fn = call.get("function", {})
                                tool_calls.append({
                                    "id": f"call_ollama_{idx}",
                                    "name": fn.get("name"),
                                    "arguments": fn.get("arguments", {}),
                                })
                        except Exception:
                            continue
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
                    "id": f"call_ollama_{idx}",
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments", {}),
                })

            return content, tool_calls
