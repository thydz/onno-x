import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from onno_x.config import Config, ModelSpec, save_config
from onno_x.persistence import save_session
from onno_x.providers import get_provider
from onno_x.skills import list_skills
from onno_x.tools import execute_tool, get_active_tool_definitions
from onno_x.tools.fs import set_active_session_for_fs
from onno_x.ui import console, print_markdown, print_tool_call, print_tool_result


def build_system_prompt(plan_mode: bool = False, extra_dirs: Optional[List[str]] = None) -> str:
    cwd = Path.cwd().resolve()
    try:
        entries = sorted([p.name + ("/" if p.is_dir() else "") for p in cwd.iterdir() if not p.name.startswith(".")])
        root_summary = ", ".join(entries[:30]) or "(empty directory)"
        if len(entries) > 30:
            root_summary += f" ... (+{len(entries)-30} more)"
    except Exception:
        root_summary = "(unknown)"

    extra_dirs_str = ""
    if extra_dirs:
        extra_dirs_str = "\nAdditional accessible directories: " + ", ".join(extra_dirs)

    skills = list_skills()
    skills_note = (
        f"\n\nYou have access to {len(skills)} specialized skills. "
        "Use search_skills(query) to find skills and load_skill(skill_name) to load their workflow instructions when needed."
    )

    # Load local project instructions if present (ONNO.md or CLAUDE.md)
    proj_notes = ""
    for note_path in [cwd / "ONNO.md", cwd / "CLAUDE.md"]:
        if note_path.exists():
            try:
                snippet = note_path.read_text(encoding="utf-8", errors="replace")[:1000]
                proj_notes += f"\n\nProject Instructions ({note_path.name}):\n{snippet}\n"
                break
            except Exception:
                pass

    plan_instruction = ""
    if plan_mode:
        plan_instruction = (
            "\n\n[PLAN MODE ACTIVE]\n"
            "You are currently in Plan Mode. Read files, explore the architecture, search code, and design a concrete, "
            "step-by-step implementation plan. DO NOT write or edit code yet. Focus on architecture, critical files, and trade-offs."
        )

    return f"""You are onno-x, an expert terminal coding agent.
Working Directory: {cwd}
Root Files: {root_summary}{extra_dirs_str}{plan_instruction}

You have tools to read, write, edit, and delete files, search code (grep), list directories, run shell commands, browse web pages, search the web, and load custom skills.
Rules:
1. Always prefer using tools to verify facts, find files, or run tests rather than guessing.
2. When creating or modifying code, keep changes minimal and clean. Prefer edit_file for precise edits over write_file.
3. Be concise and direct.{skills_note}{proj_notes}
"""


class AgentSession:
    def __init__(self, config: Config, session_id: Optional[str] = None):
        self.config = config
        self.session_id = session_id or f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.fast_mode = False
        self.plan_mode = False
        self.permission_mode = "auto"  # "auto", "manual", "all"
        self.permission_handler: Optional[Callable[[str, Dict[str, Any], str], str]] = None
        self.output_style = "default"  # default, concise, verbose
        self.advisor_model: Optional[str] = None
        self.extra_dirs: List[str] = []
        self.checkpoints: List[Dict[str, Any]] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.turns_count = 0
        self.notify_completion = True
        self.cancel_requested = threading.Event()
        self.spec: ModelSpec = config.models.get(
            config.active_model,
            list(config.models.values())[0] if config.models else None,
        )
        if not self.spec:
            raise ValueError(f"No valid model configured for '{config.active_model}'")
        self.provider = get_provider(self.spec)
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt()}
        ]
        set_active_session_for_fs(self)

    def add_directory(self, path_str: str) -> bool:
        p = Path(path_str).expanduser().resolve()
        if p.exists() and p.is_dir():
            s = str(p)
            if s not in self.extra_dirs:
                self.extra_dirs.append(s)
                self.refresh_system_prompt()
            return True
        return False

    def change_directory(self, path_str: str) -> bool:
        p = Path(path_str).expanduser().resolve()
        if p.exists() and p.is_dir():
            os.chdir(str(p))
            self.refresh_system_prompt()
            return True
        return False

    def toggle_plan_mode(self, state: Optional[bool] = None) -> bool:
        self.plan_mode = not self.plan_mode if state is None else state
        self.refresh_system_prompt()
        return self.plan_mode

    def toggle_fast_mode(self) -> bool:
        self.fast_mode = not self.fast_mode
        if self.fast_mode:
            self.spec.temperature = 0.0
        else:
            self.spec.temperature = 0.2
        return self.fast_mode

    def set_output_style(self, style: str) -> str:
        self.output_style = style.lower()
        return self.output_style

    def set_effort(self, level: str) -> str:
        l = level.lower()
        if l in ("low", "min"):
            self.spec.temperature = 0.0
            return "low (temp=0.0)"
        elif l in ("high", "max"):
            self.spec.temperature = 0.5
            return "high (temp=0.5)"
        else:
            self.spec.temperature = 0.2
            return "medium/auto (temp=0.2)"

    def refresh_system_prompt(self) -> None:
        self.messages[0] = {
            "role": "system",
            "content": build_system_prompt(plan_mode=self.plan_mode, extra_dirs=self.extra_dirs)
        }

    def refresh_skills(self) -> None:
        from onno_x.skills import list_skills
        list_skills(force_reload=True)
        self.refresh_system_prompt()

    def create_checkpoint(self) -> None:
        """Save message history and file snapshot tracking container."""
        self.checkpoints.append({
            "messages": [dict(m) for m in self.messages],
            "file_snapshots": {},
        })
        if len(self.checkpoints) > 10:
            self.checkpoints.pop(0)

    def rewind_checkpoint(self) -> Dict[str, Any]:
        """Revert messages and restore files modified in the checkpoint."""
        if not self.checkpoints:
            return {"reverted": False, "files_restored": []}
        cp = self.checkpoints.pop()
        if isinstance(cp, dict):
            self.messages = cp.get("messages", self.messages)
            snapshots = cp.get("file_snapshots", {})
        else:
            self.messages = cp
            snapshots = {}

        restored_files = []
        for file_path_str, original_content in snapshots.items():
            p = Path(file_path_str)
            try:
                if original_content is None:
                    if p.exists():
                        if p.is_file():
                            p.unlink()
                            restored_files.append(f"Deleted created file: {p.name}")
                        elif p.is_dir():
                            shutil.rmtree(p)
                            restored_files.append(f"Deleted created dir: {p.name}")
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(original_content, encoding="utf-8")
                    restored_files.append(f"Restored: {p.name}")
            except Exception as e:
                restored_files.append(f"Failed to restore {p.name}: {e}")

        return {"reverted": True, "files_restored": restored_files}

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": build_system_prompt(plan_mode=self.plan_mode, extra_dirs=self.extra_dirs)}]
        self.turns_count = 0
        self.checkpoints.clear()

    def save(self) -> Path:
        """Explicitly save current session to disk."""
        return save_session(
            session_id=self.session_id,
            messages=self.messages,
            model_name=self.spec.name,
            turns_count=self.turns_count,
            permission_mode=self.permission_mode,
            plan_mode=self.plan_mode,
        )

    def restore_from_dict(self, data: Dict[str, Any]) -> bool:
        """Restore session state from saved dictionary."""
        self.session_id = data.get("session_id", self.session_id)
        self.messages = data.get("messages", self.messages)
        self.turns_count = data.get("turns_count", len([m for m in self.messages if m.get("role") == "user"]))
        self.permission_mode = data.get("permission_mode", "auto")
        self.plan_mode = data.get("plan_mode", False)
        model_name = data.get("model_name")
        if model_name and model_name in self.config.models:
            self.switch_model(model_name)
        return True

    def set_permission_mode(self, mode: str) -> str:
        m = mode.lower().strip()
        if m in ("all", "accept-all", "accept_all", "yolo", "allow"):
            self.permission_mode = "all"
        elif m in ("manual", "ask", "strict"):
            self.permission_mode = "manual"
        else:
            self.permission_mode = "auto"
        return self.permission_mode

    def compact(self, keep_last_turns: int = 2) -> int:
        """Atomic turn-based compaction that never breaks tool_call / tool_result pairs."""
        if len(self.messages) <= 2:
            return 0
        sys_prompt = self.messages[0]

        # Find all user turn starting indices
        user_indices = [i for i, m in enumerate(self.messages) if m.get("role") == "user"]
        if len(user_indices) > keep_last_turns:
            start_idx = user_indices[-keep_last_turns]
            orig_len = len(self.messages)
            # Ensure start_idx does not split into a middle of a tool response
            while start_idx < len(self.messages) and self.messages[start_idx].get("role") == "tool":
                start_idx += 1
            self.messages = [sys_prompt] + self.messages[start_idx:]
            return orig_len - len(self.messages)
        return 0

    def switch_model(self, model_name: str) -> bool:
        if model_name not in self.config.models:
            return False
        self.config.active_model = model_name
        self.spec = self.config.models[model_name]
        self.provider = get_provider(self.spec)
        try:
            save_config(self.config)
        except Exception:
            pass
        return True

    def _auto_trim_context_if_needed(self) -> None:
        # Dynamically set compact threshold based on active model's context capacity
        model_name = (self.spec.name or "").lower()
        model_id = (getattr(self.spec, "model_id", "") or "").lower()
        max_cfg_tokens = getattr(self.spec, "max_tokens", 4096)

        is_large_model = (
            "router" in model_name
            or "gemini" in model_name
            or "gemini" in model_id
            or max_cfg_tokens >= 60000
        )
        trim_threshold = 80000 if is_large_model else 3200

        # Realistic token ratio (approx 2.8 chars per token for mixed code, diffs, tool JSON)
        est_tokens = int(sum(len(str(m.get("content", ""))) for m in self.messages) / 2.8)
        if est_tokens > trim_threshold and len(self.messages) > 4:
            console.print(f"[dim yellow]⚡ Auto-compacting context buffer (> {trim_threshold} tokens)...[/dim yellow]")
            self.compact(keep_last_turns=2)

    def run_turn(
        self,
        user_input: str,
        max_steps: Optional[int] = None,
        ephemeral: bool = False,
        on_output: Optional[Callable[[Any], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str, str], None]] = None,
    ) -> Optional[str]:
        self.cancel_requested.clear()
        self.create_checkpoint()
        self.messages.append({"role": "user", "content": user_input})
        self.turns_count += 1
        turn_start_time = time.time()

        # Determine step budget based on model capacity and config (default 50-100 steps)
        is_large_model = (
            "router" in (self.spec.name or "").lower()
            or getattr(self.spec, "max_tokens", 0) >= 60000
        )
        default_steps = 100 if is_large_model else 50
        limit_steps = max_steps or getattr(self.config, "max_steps", default_steps)

        final_response = ""
        steps = 0
        active_tools = get_active_tool_definitions()

        try:
            while steps < limit_steps:
                if self.cancel_requested.is_set():
                    if on_output:
                        on_output(Panel("[bold yellow]⚡ Turn interrupted by user (ESC).[/bold yellow]", border_style="yellow"))
                    break

                steps += 1
                self._auto_trim_context_if_needed()

                in_tokens = sum(len(str(m.get("content", ""))) for m in self.messages) // 4
                self.total_input_tokens += in_tokens

                streamed_chunks: List[str] = []
                status = None
                if not on_output:
                    status = console.status(f"[bold cyan]Thinking [/bold cyan]")
                    status.start()

                if on_status:
                    if steps == 1:
                        on_status("thinking", f"🧠 Membaca konteks & berpikir ")
                    else:
                        on_status("thinking", f"🧠 Menganalisis hasil tool ")

                def on_chunk(token: str):
                    if self.cancel_requested.is_set():
                        raise InterruptedError("Turn cancelled by user")
                    if status and not streamed_chunks:
                        try:
                            status.stop()
                        except Exception:
                            pass
                    streamed_chunks.append(token)
                    if on_token:
                        try:
                            on_token(token)
                        except Exception:
                            pass
                    elif not on_output:
                        import sys
                        sys.stdout.write(token)
                        sys.stdout.flush()

                try:
                    content, tool_calls = self.provider.chat(
                        messages=self.messages,
                        tools=active_tools,
                        on_chunk=on_chunk,
                    )
                except Exception as e:
                    if status:
                        try:
                            status.stop()
                        except Exception:
                            pass
                    err_str = str(e).lower()
                    if "exceed" in err_str or "context" in err_str or "n_ctx" in err_str:
                        console.print("[bold yellow]⚡ Exceeded model context size! Auto-compacting and retrying...[/bold yellow]")
                        self.compact(keep_last_turns=2)
                        try:
                            with console.status(f"[bold cyan]Retrying [/bold cyan]"):
                                content, tool_calls = self.provider.chat(
                                    messages=self.messages,
                                    tools=active_tools,
                                )
                        except Exception as retry_err:
                            if on_output:
                                on_output(Panel(f"[bold red]Provider error after compact:[/bold red] {str(retry_err)}", border_style="red"))
                            else:
                                console.print(f"[bold red]Provider error after compact:[/bold red] {str(retry_err)}")
                            break
                    else:
                        error_panel = Panel(
                            f"[bold red]Provider Error ({self.spec.name}):[/bold red] {str(e)}\n\n"
                            "[dim]Tips: Server model mungkin mengalami timeout atau tidak merespons. "
                            "Coba beralih ke model cloud/router yang aktif dengan perintah `/model 9router`.[/dim]",
                            border_style="red",
                            title="Error Model Provider",
                            title_align="left",
                        )
                        if on_output:
                            on_output(error_panel)
                        else:
                            console.print(f"[bold red]Provider error:[/bold red] {str(e)}")
                        break
                finally:
                    try:
                        status.stop()
                    except Exception:
                        pass

                if streamed_chunks and not on_output:
                    import sys
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                elif content:
                    if on_output:
                        on_output(Markdown(content))
                    else:
                        print_markdown(content)

                if content:
                    out_tokens = len(content) // 4
                    self.total_output_tokens += out_tokens
                    final_response += content

                if not tool_calls:
                    if content:
                        self.messages.append({"role": "assistant", "content": content})
                    break

                assistant_msg: Dict[str, Any] = {"role": "assistant"}
                if content:
                    assistant_msg["content"] = content
                else:
                    assistant_msg["content"] = None

                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else str(tc["arguments"]),
                        },
                    }
                    for tc in tool_calls
                ]
                self.messages.append(assistant_msg)

                for tc in tool_calls:
                    if self.cancel_requested.is_set():
                        if on_output:
                            on_output(Panel("[bold yellow]⚡ Remaining tool calls cancelled by user (ESC).[/bold yellow]", border_style="yellow"))
                        break
                    call_id = tc["id"]
                    tool_name = tc["name"]
                    args = tc["arguments"]

                    if on_status:
                        # Determine human-friendly detail description
                        detail = f"⚙️ Menjalankan: {tool_name}"
                        import os
                        if tool_name == "read_file":
                            p = args.get("path", "") if isinstance(args, dict) else ""
                            detail = f"📖 Membaca: {os.path.basename(str(p)) or p}"
                        elif tool_name in ("write_file", "edit_file"):
                            p = args.get("path", "") if isinstance(args, dict) else ""
                            detail = f"✏️ Menulis: {os.path.basename(str(p)) or p}"
                        elif tool_name == "run_shell":
                            cmd = args.get("command", "") if isinstance(args, dict) else str(args)
                            detail = f"⚙️ Terminal: {cmd[:30]}"
                        elif tool_name == "web_search":
                            q = args.get("query", "") if isinstance(args, dict) else str(args)
                            detail = f"🔍 Mencari web: {q[:30]}"
                        elif tool_name == "fetch_url":
                            u = args.get("url", "") if isinstance(args, dict) else str(args)
                            detail = f"🌐 Mengunduh web: {u[:30]}"
                        elif tool_name == "grep":
                            pt = args.get("pattern", "") if isinstance(args, dict) else str(args)
                            detail = f"🔎 Mencari kode: {pt[:25]}"
                        elif tool_name == "list_dir":
                            p = args.get("path", "") if isinstance(args, dict) else "."
                            detail = f"📁 Melihat folder: {p}"
                        on_status("tool", detail)

                    if on_output:
                        on_output(Text.assemble(("⚙ Executing tool: ", "bold yellow"), (tool_name, "bold green"), (f" {args}", "dim")))
                    else:
                        print_tool_call(tool_name, args)

                    result = execute_tool(tool_name, args, permission_mode=self.permission_mode, session=self)

                    if on_output:
                        snippet = result.strip()
                        if len(snippet) > 800:
                            snippet = snippet[:800] + "\n... (truncated)"
                        on_output(Panel(snippet, border_style="dim white", title="Tool Output", title_align="left"))
                    else:
                        print_tool_result(result)

                    stored_result = result
                    if len(stored_result) > 2000:
                        stored_result = stored_result[:2000] + "\n... (truncated to fit context window)"

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": stored_result,
                    })

            # If step limit was reached and last message is a tool response, synthesize conclusions
            if steps >= limit_steps and self.messages and self.messages[-1].get("role") == "tool":
                if on_status:
                    on_status("thinking", f"🧠 Menyusun laporan akhir ({self.spec.name})...")
                try:
                    synthesis_content, _ = self.provider.chat(
                        messages=self.messages + [{
                            "role": "user",
                            "content": "Batas langkah tercapai. Sintesiskan semua temuan di atas dan berikan laporan audit/ringkasan lengkap sekarang."
                        }],
                        tools=[],
                        on_chunk=on_chunk,
                    )
                    if synthesis_content:
                        if on_output:
                            on_output(Markdown(synthesis_content))
                        else:
                            print_markdown(synthesis_content)
                        final_response += synthesis_content
                        self.messages.append({"role": "assistant", "content": synthesis_content})
                except Exception:
                    pass

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚡ Operation interrupted by user (Ctrl+C).[/bold yellow]")
            return final_response

        if ephemeral:
            # Revert history if run in side-question mode (/btw)
            self.rewind_checkpoint()
        else:
            # Auto-save session state to disk
            try:
                save_session(
                    session_id=self.session_id,
                    messages=self.messages,
                    model_name=self.spec.name,
                    turns_count=self.turns_count,
                    permission_mode=self.permission_mode,
                    plan_mode=self.plan_mode,
                )
            except Exception:
                pass

        # Turn completion status line matching Claude Code (* Worked for Xs · done HH:MM PM)
        elapsed = time.time() - turn_start_time
        import datetime
        now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
        summary_str = f"* Worked for {elapsed:.1f}s · done {now_str}"
        if on_output:
            on_output(Text(f"\n{summary_str}\n", style="dim"))
        else:
            console.print(f"\n[dim]{summary_str}[/dim]\n")

        # Audio completion alert if turn was longer than 8 seconds
        if elapsed > 8.0 and self.notify_completion:
            import sys
            sys.stdout.write("\a")
            sys.stdout.flush()

        return final_response
