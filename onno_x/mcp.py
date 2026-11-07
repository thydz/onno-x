import atexit
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def sanitize_json_schema(schema: Any) -> Any:
    """Sanitize draft-07/2020-12 JSON Schemas into OpenAI/Gemini/Claude compliant OpenAPI 3.0 schema."""
    if not isinstance(schema, dict):
        return schema

    cleaned = {}
    for k, v in schema.items():
        # Remove meta schemas that strict LLM proxies (Google/OpenAI/Anthropic) reject
        if k in ("$schema", "$id", "propertyNames", "additionalItems"):
            continue

        if k == "description" and isinstance(v, str) and len(v) > 200:
            cleaned[k] = v[:197] + "..."
            continue

        if k == "items":
            if isinstance(v, list):
                # Tuple validation: convert to single schema object
                cleaned[k] = sanitize_json_schema(v[0]) if v else {"type": "string"}
            elif isinstance(v, dict):
                cleaned[k] = sanitize_json_schema(v)
            else:
                cleaned[k] = {"type": "string"}
        elif isinstance(v, dict):
            cleaned[k] = sanitize_json_schema(v)
        elif isinstance(v, list):
            cleaned[k] = [sanitize_json_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            cleaned[k] = v

    return cleaned


class MCPServerProcess:
    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}
        self.proc: Optional[subprocess.Popen] = None
        self.req_id = 0
        self.tools: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Start server subprocess and perform JSON-RPC handshake."""
        full_env = os.environ.copy()
        full_env.update(self.env)
        cmd = [self.command] + self.args
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Prevent pipe buffer deadlock when child emits logs
                text=True,
                bufsize=1,
                env=full_env,
            )
            # 1. Initialize
            init_resp = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "onno-x", "version": "1.0"},
            }, timeout=8.0)
            if not init_resp:
                return False

            # 2. Initialized notification
            self._send_notification("notifications/initialized", {})

            # 3. Fetch tools
            tools_resp = self._send_request("tools/list", {}, timeout=8.0)
            if tools_resp and "tools" in tools_resp:
                self.tools = tools_resp["tools"]
            return True
        except Exception:
            return False

    def _send_request(self, method: str, params: dict, timeout: float = 10.0) -> Optional[dict]:
        with self._lock:
            if not self.proc or self.proc.poll() is not None:
                return None
            self.req_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": self.req_id,
                "method": method,
                "params": params,
            }
            try:
                msg = json.dumps(payload) + "\n"
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()

                # Read line response with select timeout to prevent any permanent freeze
                import select, time
                deadline = time.time() + timeout
                while time.time() < deadline:
                    remain = max(0.05, deadline - time.time())
                    rlist, _, _ = select.select([self.proc.stdout], [], [], remain)
                    if not rlist:
                        return None
                    line = self.proc.stdout.readline()
                    if not line:
                        return None
                    line = line.strip()
                    if not line:
                        continue
                    if "jsonrpc" in line and line.startswith("{"):
                        try:
                            data = json.loads(line)
                            return data.get("result")
                        except Exception:
                            continue
                return None
            except Exception:
                return None

    def _send_notification(self, method: str, params: dict) -> None:
        with self._lock:
            if not self.proc or self.proc.poll() is not None:
                return
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
            try:
                msg = json.dumps(payload) + "\n"
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            except Exception:
                pass

    def call_tool(self, tool_name: str, args: dict) -> str:
        res = self._send_request("tools/call", {"name": tool_name, "arguments": args}, timeout=30.0)
        if not res:
            return f"Error: MCP Server '{self.name}' returned empty or timed out on tool '{tool_name}'"
        content = res.get("content", [])
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and "text" in c]
            return "\n".join(texts) or json.dumps(content)
        return str(res)

    def close(self):
        if self.proc:
            try:
                if self.proc.stdin:
                    try:
                        self.proc.stdin.close()
                    except Exception:
                        pass
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None


class MCPManager:
    _instance = None

    def __init__(self):
        self.servers: Dict[str, MCPServerProcess] = {}
        self.server_configs: Dict[str, dict] = {}
        self.tool_map: Dict[str, Tuple[MCPServerProcess, str]] = {}
        self.load_configs()
        atexit.register(self.cleanup)

    @classmethod
    def get_instance(cls) -> "MCPManager":
        if cls._instance is None:
            cls._instance = MCPManager()
        return cls._instance

    def cleanup(self):
        """Close and terminate all running server subprocesses."""
        for s in list(self.servers.values()):
            s.close()
        self.servers.clear()
        self.tool_map.clear()

    def load_configs(self) -> None:
        """Find and parse .mcp.json or mcp.json files."""
        candidates = [
            Path.cwd() / ".mcp.json",
            Path.cwd() / "mcp.json",
            Path.home() / ".onno-x" / "mcp.json",
        ]
        config_data = {}
        for p in candidates:
            if p.exists():
                try:
                    loaded = json.loads(p.read_text(encoding="utf-8"))
                    srvs = loaded.get("mcpServers") or loaded.get("servers") or {}
                    config_data.update(srvs)
                except Exception:
                    pass

        self.cleanup()
        self.server_configs = config_data

        if not config_data:
            return

        from concurrent.futures import ThreadPoolExecutor

        def _init_server(item):
            s_name, s_cfg = item
            cmd = s_cfg.get("command")
            args = s_cfg.get("args", [])
            env = s_cfg.get("env", {})
            if cmd:
                proc = MCPServerProcess(s_name, cmd, args, env)
                if proc.start():
                    return s_name, proc
            return None

        with ThreadPoolExecutor(max_workers=min(len(config_data), 4)) as executor:
            results = list(executor.map(_init_server, config_data.items()))

        for res in results:
            if res:
                s_name, proc = res
                self.servers[s_name] = proc
                for t in proc.tools:
                    tool_id = f"mcp__{s_name}__{t['name']}"
                    self.tool_map[tool_id] = (proc, t["name"])

    def get_tool_definitions(self, max_direct_tools_per_server: int = 4) -> List[Dict[str, Any]]:
        """
        Return registered MCP tools in OpenAI/Claude function format.
        Expose top essential tools + universal dynamic runner `run_<server>_tool(tool_name, arguments)`
        and `search_<server>_tools(query)`.
        Keeps tool schema payload compact (~2,500 tokens) to fit inside local LLM 8K context windows.
        """
        defs = []
        for s_name, proc in self.servers.items():
            cfg = self.server_configs.get(s_name, {})
            expose_all = cfg.get("exposeAll", False)

            if expose_all or len(proc.tools) <= max_direct_tools_per_server:
                # Direct exposure of tools
                for t in proc.tools:
                    tool_id = f"mcp__{s_name}__{t['name']}"
                    defs.append({
                        "type": "function",
                        "function": {
                            "name": tool_id,
                            "description": f"[{s_name} MCP] " + t.get("description", ""),
                            "parameters": sanitize_json_schema(t.get("inputSchema", {"type": "object", "properties": {}})),
                        },
                    })
            else:
                # Server has a large suite (e.g. HexStrike 184 tools, or api-anything).
                # 1. Provide universal runner tool to execute ANY tool
                defs.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp__{s_name}__run_tool",
                        "description": (
                            f"Execute any of the {len(proc.tools)} tools provided by {s_name} MCP server "
                            "(e.g. nmap_scan, sqlmap_scan, nuclei_scan, subfinder_scan, ffuf_scan, metasploit_run, etc.)."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "description": f"The exact name of the {s_name} tool to execute.",
                                },
                                "arguments": {
                                    "type": "object",
                                    "description": "Arguments/payload dictionary to pass to the tool.",
                                },
                            },
                            "required": ["tool_name"],
                        },
                    },
                })

                # 2. Provide tool search helper
                defs.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp__{s_name}__search_tools",
                        "description": f"Search available tools and their parameter schemas in the {s_name} suite by keyword or category.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Keyword to search tool names and descriptions (e.g. 'web', 'scan', 'cve', 'subdomain', 'exploit')",
                                    "default": "",
                                },
                            },
                        },
                    },
                })

                # 3. Direct exposure of top essential tools for zero-shot convenience
                priority_names = {
                    "nmap_scan", "nuclei_scan", "sqlmap_scan"
                }
                for t in proc.tools:
                    if t["name"] in priority_names:
                        defs.append({
                            "type": "function",
                            "function": {
                                "name": f"mcp__{s_name}__{t['name']}",
                                "description": f"[{s_name} MCP] " + t.get("description", ""),
                                "parameters": sanitize_json_schema(t.get("inputSchema", {"type": "object", "properties": {}})),
                            },
                        })

        return defs

    def execute_tool(self, tool_id: str, args: dict) -> Optional[str]:
        # Handle universal router runner
        for s_name, proc in self.servers.items():
            if tool_id == f"mcp__{s_name}__run_tool":
                target_tool = args.get("tool_name", "").strip()
                target_args = args.get("arguments", {})
                return proc.call_tool(target_tool, target_args)

            if tool_id == f"mcp__{s_name}__search_tools":
                q = args.get("query", "").lower()
                matches = []
                for t in proc.tools:
                    if not q or q in t["name"].lower() or q in t.get("description", "").lower():
                        matches.append(f"• {t['name']}: {t.get('description', '')[:90]}")
                summary = f"Found {len(matches)} {s_name} tools matching '{q}':\n" + "\n".join(matches[:25])
                if len(matches) > 25:
                    summary += f"\n... (+{len(matches)-25} more tools available)"
                return summary

        if tool_id in self.tool_map:
            proc, orig_tool_name = self.tool_map[tool_id]
            return proc.call_tool(orig_tool_name, args)
        return None

