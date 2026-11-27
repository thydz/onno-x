import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape as _escape_markup
from onno_x.config import Config, ModelSpec, save_config
from onno_x.persistence import save_session
from onno_x.providers import get_provider
from onno_x.skills import invalidate_skills_cache, list_skills
from onno_x.tools import execute_tool, get_active_tool_definitions
from onno_x.tools.fs import set_active_session_for_fs
from onno_x.ui import console, print_markdown, print_tool_call, print_tool_result


# Rough token estimate: mixed code/diffs/tool JSON run close to 4 chars per token.
CHARS_PER_TOKEN = 4

# Tools with no shared state and no side effects: consecutive calls of these can
# run together instead of one after another.
READONLY_TOOLS = frozenset({
    "read_file",
    "list_dir",
    "grep_search",
    "web_search",
    "fetch_url",
    "load_skill",
    "search_skills",
    "obsidian_search_notes",
    "obsidian_read_note",
})


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """Approximate the input size of a request, including tool arguments.

    Assistant messages that only call tools carry no `content`, so summing
    `content` alone made long tool loops look far cheaper than they are.
    """
    total = 0
    for m in messages:
        total += len(str(m.get("content") or ""))
        if m.get("tool_calls"):
            total += len(json.dumps(m["tool_calls"], ensure_ascii=False, default=str))
    return max(total // CHARS_PER_TOKEN, 1)


def estimate_output_tokens(content: str, tool_calls: Optional[List[Dict[str, Any]]]) -> int:
    """Approximate generated tokens for one provider response."""
    total = len(content or "")
    if tool_calls:
        total += len(json.dumps(tool_calls, ensure_ascii=False, default=str))
    return total // CHARS_PER_TOKEN


OUTPUT_STYLE_INSTRUCTIONS = {
    "concise": "Reply tersuccinct: short sentences, no restating the question, minimal preamble. Code and diffs stay complete.",
    "verbose": "Explain reasoning and trade-offs step by step; spell out assumptions before acting.",
}

# Providers disagree on the tag name (and some emit several blocks per reply),
# so strip every common variant instead of only the first  block.
_REASONING_BLOCK = re.compile(
    r"<\s*(?:think|thinking|reasoning)\s*>.*?<\s*/\s*(?:think|thinking|reasoning)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_REASONING_OPEN = re.compile(r"<\s*(?:think|thinking|reasoning)\s*>", re.IGNORECASE)
_REASONING_CLOSE = re.compile(r"<\s*/\s*(?:think|thinking|reasoning)\s*>", re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove model reasoning blocks, including an unterminated final block."""
    if not text:
        return ""
    cleaned = _REASONING_BLOCK.sub("", text)
    # An open tag with no matching close means everything after it is still
    # reasoning (streaming truncation or a provider that omitted the close).
    cleaned = _REASONING_OPEN.split(cleaned, maxsplit=1)[0]
    return _REASONING_CLOSE.sub("", cleaned)


def build_system_prompt(
    plan_mode: bool = False,
    extra_dirs: Optional[List[str]] = None,
    goal: Optional[str] = None,
    output_style: Optional[str] = None,
    todos: Optional[List[Dict[str, Any]]] = None,
) -> str:
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
                full = note_path.read_text(encoding="utf-8", errors="replace")
                # /memory edit appends to this file, so a 1KB cut silently dropped
                # every instruction added after the first few entries.
                snippet = full[:8000]
                if len(full) > 8000:
                    snippet += f"\n... ({len(full) - 8000} chars truncated; read {note_path.name} for the rest)"
                proj_notes += f"\n\nProject Instructions ({note_path.name}):\n{snippet}\n"
                break
            except Exception:
                pass

    goal_instruction = ""
    if goal:
        goal_instruction = (
            "\n\n[ACTIVE GOAL]\n"
            f"{goal}\n"
            "Keep working toward this goal until it is verifiably done; state clearly when it is."
        )

    todo_instruction = ""
    if todos:
        lines = [
            f"{'[x]' if t.get('done') else '[ ]'} {t.get('text', '').strip()}"
            for t in todos
            if str(t.get("text", "")).strip()
        ]
        if lines:
            todo_instruction = (
                "\n\n[TASK LIST]\n" + "\n".join(lines)
                + "\nKeep this list current: mark items done as you finish them, "
                "and do not claim an item is done unless it is verified."
            )

    style_instruction = ""
    style_note = OUTPUT_STYLE_INSTRUCTIONS.get((output_style or "default").lower())
    if style_note:
        style_instruction = f"\n\n[OUTPUT STYLE: {output_style.lower()}]\n{style_note}"

    plan_instruction = ""
    if plan_mode:
        plan_instruction = (
            "\n\n[PLAN MODE ACTIVE]\n"
            "You are currently in Plan Mode. Read files, explore the architecture, search code, and design a concrete, "
            "step-by-step implementation plan. DO NOT write or edit code yet. Focus on architecture, critical files, and trade-offs."
        )

    return f"""You are onno-x, an expert terminal coding agent.
Working Directory: {cwd}
Root Files: {root_summary}{extra_dirs_str}{plan_instruction}{goal_instruction}{style_instruction}{todo_instruction}

You have tools to read, write, edit, and delete files, search code (grep), list directories, run shell commands, browse web pages, search the web, and load custom skills.
Rules:
1. Always prefer using tools to verify facts, find files, or run tests rather than guessing.
2. When creating or modifying code, keep changes minimal and clean. Prefer edit_file for precise edits over write_file.
3. Be concise and direct.
4. Bahasa & Komunikasi: Selalu berikan seluruh respons, penjelasan, laporan, dan analisis dalam Bahasa Indonesia yang lugas, komunikatif, dan profesional. (Biarkan sintaks kode, nama fungsi/file, dan istilah teknis khusus tetap dalam bentuk aslinya).{skills_note}{proj_notes}
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
        self.goal: Optional[str] = None
        self.todos: List[Dict[str, Any]] = []
        self.title: Optional[str] = None
        self.extra_dirs: List[str] = []
        self.checkpoints: List[Dict[str, Any]] = []
        # Named checkpoints (/snapshot, /restore) live in memory only: they are
        # recovery points for this session, not file format on disk.
        self.named_checkpoints: Dict[str, Dict[str, Any]] = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        # Size of the history sent in the most recent request (context window
        # pressure), as opposed to total_input_tokens which accumulates every
        # request of every step.
        self.last_input_tokens = 0
        self.turns_count = 0
        self.notify_completion = bool(getattr(config, "notify_completion", True))
        self.cancel_requested = threading.Event()
        # Paths changed during the current turn, used by auto-verify and /diff.
        self.turn_edited_paths: List[str] = []
        self.last_verify: Optional[Dict[str, Any]] = None
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
            # Repo/local skill dirs are cwd-relative, so the cached listing is stale.
            invalidate_skills_cache()
            self.refresh_system_prompt()
            return True
        return False

    def toggle_plan_mode(self, state: Optional[bool] = None) -> bool:
        self.plan_mode = not self.plan_mode if state is None else state
        self.refresh_system_prompt()
        return self.plan_mode

    def toggle_fast_mode(self) -> bool:
        self.fast_mode = not self.fast_mode
        self.spec.temperature = 0.0 if self.fast_mode else 0.2
        self._persist_spec()
        return self.fast_mode

    def set_output_style(self, style: str) -> str:
        self.output_style = style.lower()
        # The style only matters if the model is told about it.
        self.refresh_system_prompt()
        return self.output_style

    def _persist_spec(self) -> None:
        """Temperature lives on the shared ModelSpec; save so it survives restarts."""
        try:
            save_config(self.config)
        except Exception:
            pass

    def set_effort(self, level: str) -> str:
        l = level.lower()
        if l in ("low", "min"):
            self.spec.temperature = 0.0
            label = "low (temp=0.0)"
        elif l in ("high", "max"):
            self.spec.temperature = 0.5
            label = "high (temp=0.5)"
        else:
            self.spec.temperature = 0.2
            label = "medium/auto (temp=0.2)"
        self._persist_spec()
        return label

    def refresh_system_prompt(self) -> None:
        self.messages[0] = {
            "role": "system",
            "content": build_system_prompt(
                plan_mode=self.plan_mode,
                extra_dirs=self.extra_dirs,
                goal=self.goal,
                output_style=self.output_style,
                todos=self.todos,
            ),
        }

    def set_goal(self, goal: Optional[str]) -> Optional[str]:
        """Pin (or clear) a goal that survives compaction and reloads."""
        cleaned = (goal or "").strip() or None
        self.goal = cleaned
        self.refresh_system_prompt()
        return self.goal

    def _snapshot_for_rewind(self, path_value: Any) -> None:
        """Record a file's content before a tool mutates it, so /rewind restores it.

        Snapshots live on the newest checkpoint. A path that did not exist yet is
        stored as None, which makes the rewind delete the file it created.
        """
        if not self.checkpoints or not path_value:
            return
        try:
            p = Path(str(path_value)).expanduser()
            key = str(p.resolve())
        except (OSError, ValueError):
            return
        snapshots = self.checkpoints[-1].setdefault("file_snapshots", {})
        if key in snapshots:
            return
        try:
            snapshots[key] = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        except OSError:
            return

    def _run_advisor(self, response: str, on_output: Optional[Callable[[Any], None]] = None) -> Optional[str]:
        """Second opinion from the /advisor model. Never breaks the main turn."""
        spec = self.config.models.get(self.advisor_model or "")
        if not spec or not response.strip():
            return None
        try:
            provider = get_provider(spec)
            critique, _ = provider.chat([
                {
                    "role": "system",
                    "content": (
                        "You are a senior reviewer. Be brief and concrete: risks, "
                        "missed edge cases, and one actionable fix. No restating."
                    ),
                },
                {"role": "user", "content": f"Review this answer:\n\n{response[:4000]}"},
            ], tools=[])
        except Exception as exc:
            msg = f"Advisor ({spec.name}) gagal: {exc}"
            if on_output:
                on_output(Text(msg, style="dim red"))
            else:
                console.print(f"[dim red]{msg}[/dim red]")
            return None

        text = (critique or "").strip()
        if text:
            panel = Panel(Text(text), title=f"Advisor ({spec.name})", border_style="magenta")
            if on_output:
                on_output(panel)
            else:
                console.print(panel)
        return text or None

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

        # Plan mode, goal and todos can change after a checkpoint was taken, so
        # rebuild the system prompt instead of keeping the snapshot's version.
        if self.messages and isinstance(self.messages[0], dict) and self.messages[0].get("role") == "system":
            self.refresh_system_prompt()

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
        # Keep the pinned goal and task list: /clear wipes the transcript,
        # not the objective or the plan.
        self.messages = [{
            "role": "system",
            "content": build_system_prompt(
                plan_mode=self.plan_mode,
                extra_dirs=self.extra_dirs,
                goal=self.goal,
                output_style=self.output_style,
                todos=self.todos,
            ),
        }]
        self.turns_count = 0
        self.checkpoints.clear()

    # --- /todo ---
    def add_todo(self, text: str) -> int:
        cleaned = (text or "").strip()
        if not cleaned:
            return 0
        self.todos.append({"text": cleaned, "done": False})
        self.refresh_system_prompt()
        return len(self.todos)

    def complete_todo(self, index: int) -> Optional[str]:
        """Toggle a 1-based item; returns its text, or None when out of range."""
        if 1 <= index <= len(self.todos):
            item = self.todos[index - 1]
            item["done"] = not item.get("done", False)
            self.refresh_system_prompt()
            return item["text"]
        return None

    def remove_todo(self, index: int) -> Optional[str]:
        if 1 <= index <= len(self.todos):
            item = self.todos.pop(index - 1)
            self.refresh_system_prompt()
            return item["text"]
        return None

    def clear_todos(self) -> None:
        self.todos.clear()
        self.refresh_system_prompt()

    # --- /snapshot, /restore, /undo-file ---
    def save_named_checkpoint(self, label: str) -> str:
        name = (label or "").strip() or f"snapshot-{len(self.named_checkpoints) + 1}"
        self.named_checkpoints[name] = {
            "messages": [dict(m) for m in self.messages],
            "turns_count": self.turns_count,
        }
        return name

    def restore_named_checkpoint(self, label: str) -> bool:
        cp = self.named_checkpoints.get((label or "").strip())
        if not cp:
            return False
        self.messages = [dict(m) for m in cp.get("messages", self.messages)]
        self.turns_count = cp.get("turns_count", self.turns_count)
        if self.messages:
            # Swap in the live prompt: flags may have changed since the snapshot.
            self.refresh_system_prompt()
        return True

    def undo_file(self, path_value: str) -> Optional[str]:
        """Restore one file from the newest checkpoint that snapshotted it."""
        try:
            key = str(Path(str(path_value)).expanduser().resolve())
        except (OSError, ValueError):
            return None
        for cp in reversed(self.checkpoints):
            snapshots = cp.get("file_snapshots") or {}
            if key not in snapshots:
                continue
            original = snapshots[key]
            p = Path(key)
            try:
                if original is None:
                    if p.exists() and p.is_file():
                        p.unlink()
                        return f"Dihapus (file dibuat setelah checkpoint): {p.name}"
                    return None
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(original, encoding="utf-8")
                return f"Dipulihkan: {p.name}"
            except OSError as exc:
                return f"Gagal memulihkan {p.name}: {exc}"
        return None

    def _state(self) -> Dict[str, Any]:
        """UI/session fields that live alongside the transcript on disk."""
        return {
            "extra_dirs": self.extra_dirs,
            "output_style": self.output_style,
            "fast_mode": self.fast_mode,
            "goal": self.goal,
            "advisor_model": self.advisor_model,
            "todos": self.todos,
            "title": self.title,
        }

    def save(self) -> Path:
        """Explicitly save current session to disk, including UI state."""
        return save_session(
            session_id=self.session_id,
            messages=self.messages,
            model_name=self.spec.name,
            turns_count=self.turns_count,
            permission_mode=self.permission_mode,
            plan_mode=self.plan_mode,
            state=self._state(),
        )

    def _save_quietly(self) -> None:
        """Persist the session, swallowing I/O errors.

        Used on turn completion and on interrupt: losing a transcript to a full
        disk or a locked file must never become a second crash on top of the
        one the user already hit.
        """
        try:
            self.save()
        except Exception:
            pass

    def restore_from_dict(self, data: Dict[str, Any]) -> bool:
        """Restore session state from saved dictionary."""
        self.session_id = data.get("session_id", self.session_id)
        self.messages = data.get("messages", self.messages)
        self.turns_count = data.get("turns_count", len([m for m in self.messages if m.get("role") == "user"]))
        self.permission_mode = data.get("permission_mode", "auto")
        self.plan_mode = data.get("plan_mode", False)
        self.extra_dirs = list(data.get("extra_dirs") or [])
        self.output_style = data.get("output_style", "default")
        self.fast_mode = bool(data.get("fast_mode", False))
        if self.fast_mode:
            self.spec.temperature = 0.0
        self.advisor_model = data.get("advisor_model")
        self.goal = data.get("goal")
        raw_todos = data.get("todos") or []
        self.todos = [
            {"text": str(t.get("text", "")), "done": bool(t.get("done"))}
            for t in raw_todos
            if isinstance(t, dict) and str(t.get("text", "")).strip()
        ]
        self.title = data.get("title")
        model_name = data.get("model_name")
        if model_name and model_name in self.config.models:
            self.switch_model(model_name)
        self.refresh_system_prompt()
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

    def compact(self, keep_last_turns: int = 2, instructions: Optional[str] = None) -> int:
        """Atomic turn-based compaction that never breaks tool_call / tool_result pairs.

        With `instructions`, the dropped block is summarised by the model first so
        the detail the user asked to keep survived the trim.
        """
        if len(self.messages) <= 2:
            return 0
        sys_prompt = self.messages[0]

        # Find all user turn starting indices
        user_indices = [i for i, m in enumerate(self.messages) if m.get("role") == "user"]
        if len(user_indices) > keep_last_turns:
            start_idx = user_indices[-keep_last_turns]
            # Ensure start_idx does not split into a middle of a tool response
            while start_idx < len(self.messages) and self.messages[start_idx].get("role") == "tool":
                start_idx += 1
            dropped = self.messages[1:start_idx]
            rest = self.messages[start_idx:]
            orig_len = len(self.messages)
            summary = self._summarize_dropped(dropped, instructions) if instructions else None
            rebuilt = [sys_prompt]
            if summary:
                rebuilt.append({
                    "role": "user",
                    "content": f"[Ringkasan konteks sebelumnya — fokus: {instructions}]\n{summary}",
                })
            self.messages = rebuilt + rest
            return orig_len - len(self.messages)
        return 0

    def _summarize_dropped(self, dropped: List[Dict[str, Any]], instructions: str) -> Optional[str]:
        """Compress dropped turns into a short note. Returns None on any failure."""
        if not dropped:
            return None
        try:
            transcript = []
            for m in dropped[-40:]:
                body = str(m.get("content") or "")[:1200]
                transcript.append(f"{m.get('role', '?')}: {body}")
            reply, _ = self.provider.chat([
                {"role": "system", "content": "Ringkas riwayat percakapan berikut menjadi catatan konteks padat. Jangan mengarang."},
                {"role": "user", "content": f"Fokus ringkasan: {instructions}\n\n" + "\n\n".join(transcript)},
            ], tools=[])
            text = (reply or "").strip()
            return text or None
        except Exception:
            return None

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

    def _parallel_readonly_groups(self, tool_calls: List[Dict[str, Any]]) -> List[List[int]]:
        """Index groups of consecutive read-only calls safe to run together.

        Manual permission mode is excluded: each tool would prompt on the same
        terminal from several threads at once.
        """
        if self.permission_mode == "manual":
            return []
        groups: List[List[int]] = []
        current: List[int] = []
        for idx, tc in enumerate(tool_calls):
            if tc.get("name") in READONLY_TOOLS and isinstance(tc.get("arguments"), dict):
                current.append(idx)
            else:
                if len(current) > 1:
                    groups.append(current)
                current = []
        if len(current) > 1:
            groups.append(current)
        return groups

    def _auto_verify(self, on_output: Optional[Callable[[Any], None]] = None) -> Optional[Dict[str, Any]]:
        """Run the project's test/lint command after this turn's edits.

        Best-effort: nothing runs unless the project advertises a command (see
        commands.detect_*), the turn actually mutated files, and /autoverify is
        on. The result is stored in ``last_verify`` for /verify and the report
        panel is rendered through on_output so the TUI never sees raw stdout.
        """
        if self.cancel_requested.is_set():
            return None
        if not self.turn_edited_paths or not getattr(self.config, "auto_verify", True):
            return None

        # Imported lazily: commands.py imports session for estimate_tokens.
        from onno_x.commands import detect_lint_command, detect_test_command, run_shell_capture

        cmd = detect_test_command() or detect_lint_command()
        if not cmd:
            return None

        notice = f"🔎 Auto-verify: {cmd} ({len(self.turn_edited_paths)} file diubah)"
        if on_output:
            on_output(Text(notice, style="dim cyan"))
        else:
            console.print(f"[dim cyan]{notice}[/dim cyan]")

        try:
            code, output = run_shell_capture(cmd, timeout=600, cancel_event=self.cancel_requested)
        except Exception as exc:
            result = {"command": cmd, "returncode": None, "output": f"gagal menjalankan: {exc}"}
            self.last_verify = result
            return result

        result = {"command": cmd, "returncode": code, "output": output}
        self.last_verify = result

        tail = (output or "").strip()
        if len(tail) > 2500:
            tail = "... (dipotong)\n" + tail[-2500:]
        title = "✔ Auto-verify lulus" if code == 0 else f"✘ Auto-verify gagal (exit {code})"
        body = f"{cmd}\n\n{tail or '(tidak ada output)'}"
        if on_output:
            on_output(Panel(Text(body), title=title, border_style="green" if code == 0 else "red"))
        else:
            console.print(Panel(
                Text(body),
                title=title,
                border_style="green" if code == 0 else "red",
            ))
        return result

    def _auto_trim_context_if_needed(self, on_output: Optional[Callable[[Any], None]] = None) -> None:
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
        configured = self.config.autocompact_threshold
        if configured is not None:
            if configured <= 0:
                return  # /autocompact off
            trim_threshold = configured
        else:
            trim_threshold = 80000 if is_large_model else 3200

        est_tokens = estimate_tokens(self.messages)
        if est_tokens > trim_threshold and len(self.messages) > 4:
            notice = f"⚡ Auto-compacting context buffer (> {trim_threshold} tokens)..."
            if on_output:
                # TUI renders through this callback; printing directly wrote
                # into the terminal underneath the full-screen app.
                on_output(Text(notice, style="dim yellow"))
            else:
                console.print(f"[dim yellow]{notice}[/dim yellow]")
            self.compact(keep_last_turns=2)

    def run_turn(
        self,
        user_input: str,
        max_steps: Optional[int] = None,
        ephemeral: bool = False,
        on_output: Optional[Callable[[Any], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str, str], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        self.cancel_requested.clear()
        self.turn_edited_paths = []
        self.create_checkpoint()
        # Ephemeral turns (/btw) rewind the transcript, so their counters have
        # to go too or /cost and /stats overstate usage.
        counters_before = (self.turns_count, self.total_input_tokens,
                           self.total_output_tokens, self.last_input_tokens)
        self.messages.append({"role": "user", "content": user_input})
        self.turns_count += 1
        turn_start_time = time.time()

        # Determine step budget based on model capacity and config (default 50-100 steps)
        is_large_model = (
            "router" in (self.spec.name or "").lower()
            or getattr(self.spec, "max_tokens", 0) >= 60000
        )
        default_steps = 100 if is_large_model else 50
        limit_steps = max(1, max_steps or getattr(self.config, "max_steps", default_steps) or default_steps)

        final_response = ""
        steps = 0
        # A provider that reports `last_truncated` stopped at max_tokens, not at
        # a real conclusion. Continuing costs another step, so cap it: past this
        # the turn ends with an explicit notice rather than a silent fragment.
        max_continuations = 3
        continuations = 0
        active_tools = get_active_tool_definitions()

        try:
            while steps < limit_steps:
                if self.cancel_requested.is_set():
                    if on_output:
                        on_output(Panel("[bold yellow]⚡ Turn interrupted by user (ESC).[/bold yellow]", border_style="yellow"))
                    break

                steps += 1
                self._auto_trim_context_if_needed(on_output)

                in_tokens = estimate_tokens(self.messages)
                self.total_input_tokens += in_tokens
                self.last_input_tokens = in_tokens

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

                was_truncated = False
                try:
                    import inspect as _inspect
                    _chat_sig = _inspect.signature(self.provider.chat)
                    _chat_kwargs = dict(
                        messages=self.messages,
                        tools=active_tools,
                        on_chunk=on_chunk,
                    )
                    if "cancel_event" in _chat_sig.parameters:
                        _chat_kwargs["cancel_event"] = self.cancel_requested
                    content, tool_calls = self.provider.chat(**_chat_kwargs)
                    was_truncated = bool(getattr(self.provider, "last_truncated", False))
                except InterruptedError:
                    # on_chunk raises this when the user pressed ESC / Stop.
                    # Stop the turn cleanly instead of reporting a provider error.
                    if on_status:
                        try:
                            on_status("thinking", "⏹ Dibatalkan oleh user")
                        except Exception:
                            pass
                    elif not on_output:
                        console.print("[bold yellow]⚡ Respons dihentikan oleh user.[/bold yellow]")
                    break
                except Exception as e:
                    if status:
                        try:
                            status.stop()
                        except Exception:
                            pass
                    err_str = str(e).lower()
                    if "exceed" in err_str or "context" in err_str or "n_ctx" in err_str:
                        notice = "⚡ Konteks model terlampaui — memadatkan lalu mencoba ulang..."
                        if on_output:
                            on_output(Text(notice, style="dim yellow"))
                        else:
                            console.print(f"[dim yellow]{notice}[/dim yellow]")
                        self.compact(keep_last_turns=2)
                        try:
                            # No console.status here: under the full-screen TUI it
                            # would paint over the app's frame.
                            retry_status = None if on_output else console.status("[bold cyan]Retrying [/bold cyan]")
                            if retry_status:
                                retry_status.start()
                            try:
                                content, tool_calls = self.provider.chat(
                                    messages=self.messages,
                                    tools=active_tools,
                                    cancel_event=self.cancel_requested,
                                )
                                was_truncated = bool(getattr(self.provider, "last_truncated", False))
                            finally:
                                if retry_status:
                                    try:
                                        retry_status.stop()
                                    except Exception:
                                        pass
                        except Exception as retry_err:
                            if on_output:
                                on_output(Panel(f"[bold red]Provider error after compact:[/bold red] {_escape_markup(str(retry_err))}", border_style="red"))
                            else:
                                console.print(f"[bold red]Provider error after compact:[/bold red] {_escape_markup(str(retry_err))}")
                            break
                    else:
                        error_panel = Panel(
                            f"[bold red]Provider Error ({_escape_markup(self.spec.name)}):[/bold red] {_escape_markup(str(e))}\n\n"
                            "[dim]Tips: Server model mungkin mengalami timeout atau tidak merespons. "
                            "Coba beralih ke model cloud/router yang aktif dengan perintah `/model 9router`.[/dim]",
                            border_style="red",
                            title="Error Model Provider",
                            title_align="left",
                        )
                        if on_output:
                            on_output(error_panel)
                        else:
                            console.print(f"[bold red]Provider error:[/bold red] {_escape_markup(str(e))}")
                        if on_error:
                            try:
                                on_error(str(e))
                            except Exception:
                                pass
                        break
                finally:
                    try:
                        status.stop()
                    except Exception:
                        pass

                if streamed_chunks:
                    if on_output and not on_token:
                        # Nobody consumed the stream (e.g. a /btw turn): render the
                        # finished text once instead of dropping it on the floor.
                        streamed_text = strip_reasoning("".join(streamed_chunks)).strip()
                        if streamed_text:
                            on_output(Markdown(streamed_text))
                    elif not on_output:
                        import sys
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                elif content:
                    clean_content = strip_reasoning(content).strip()
                    if clean_content:
                        if on_output:
                            on_output(Markdown(clean_content))
                        else:
                            print_markdown(clean_content)

                if content:
                    clean_content = strip_reasoning(content).strip()
                    self.total_output_tokens += estimate_output_tokens(content, tool_calls)
                    final_response += clean_content
                elif tool_calls:
                    # Tool-only step: no text, but the arguments are generated output.
                    self.total_output_tokens += estimate_output_tokens("", tool_calls)

                if not tool_calls:
                    if content:
                        clean_content = strip_reasoning(content).strip()
                        self.messages.append({"role": "assistant", "content": clean_content})

                    # The model ran out of output budget mid-answer. Committing
                    # this as final is what makes a build stop half-written, so
                    # ask it to resume instead — bounded, and announced.
                    if was_truncated and continuations < max_continuations:
                        continuations += 1
                        notice = (
                            f"⚡ Output terpotong (max_tokens) — melanjutkan "
                            f"{continuations}/{max_continuations}..."
                        )
                        if on_output:
                            on_output(Text(notice, style="dim yellow"))
                        else:
                            console.print(f"[dim yellow]{notice}[/dim yellow]")
                        self.messages.append({
                            "role": "user",
                            "content": (
                                "Lanjutkan tepat dari titik terakhir. Jangan ulangi bagian "
                                "yang sudah dikirim, jangan buka kalimat baru — sambung "
                                "karakter demi karakter."
                            ),
                        })
                        continue

                    if was_truncated:
                        notice = (
                            "⚡ Output masih terpotong setelah batas lanjutan — "
                            "naikkan max_tokens model ini atau minta bagian berikutnya."
                        )
                        if on_output:
                            on_output(Text(notice, style="dim yellow"))
                        else:
                            console.print(f"[dim yellow]{notice}[/dim yellow]")
                    break

                assistant_msg: Dict[str, Any] = {"role": "assistant"}
                if content:
                    clean_content = strip_reasoning(content).strip()
                    assistant_msg["content"] = clean_content
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

                # Read-only calls placed next to each other by the model are
                # independent, so start them together and still emit their
                # results in the order the model asked for them.
                executor = None
                futures: Dict[int, Any] = {}
                groups = self._parallel_readonly_groups(tool_calls)
                if groups:
                    executor = ThreadPoolExecutor(
                        max_workers=min(4, sum(len(g) for g in groups)),
                        thread_name_prefix="onno-tool",
                    )
                    for group in groups:
                        for idx in group:
                            grouped = tool_calls[idx]
                            futures[idx] = executor.submit(
                                execute_tool,
                                grouped["name"],
                                grouped["arguments"],
                                self.permission_mode,
                                self,
                            )

                answered_ids: set = set()
                for idx, tc in enumerate(tool_calls):
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

                    if on_tool_call:
                        try:
                            on_tool_call(tool_name, args)
                        except Exception:
                            pass

                    if tool_name in ("write_file", "edit_file", "delete_file") and isinstance(args, dict):
                        self._snapshot_for_rewind(args.get("path"))
                        if args.get("path") and str(args["path"]) not in self.turn_edited_paths:
                            self.turn_edited_paths.append(str(args["path"]))

                    future = futures.pop(idx, None)
                    if future is not None:
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = f"Error executing {tool_name}: {exc}"
                    else:
                        result = execute_tool(tool_name, args, permission_mode=self.permission_mode, session=self)

                    if on_tool_result:
                        try:
                            on_tool_result(tool_name, result)
                        except Exception:
                            pass

                    if on_output:
                        snippet = result.strip()
                        if len(snippet) > 800:
                            snippet = snippet[:800] + "\n... (truncated)"
                        on_output(Panel(Text(snippet), border_style="dim white", title="Tool Output", title_align="left"))
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
                    answered_ids.add(call_id)

                # A cancelled tool loop leaves the assistant message with more
                # tool_calls than tool replies; OpenAI/Anthropic then reject the
                # whole history on the next request, so close the gap here.
                for tc in tool_calls:
                    if tc["id"] in answered_ids:
                        continue
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc.get("name") or "unknown",
                        "content": "Dibatalkan oleh user sebelum tool dijalankan.",
                    })

                if executor is not None:
                    executor.shutdown(wait=True)

            # If step limit was reached and last message is a tool response, synthesize conclusions
            if steps >= limit_steps and self.messages and self.messages[-1].get("role") == "tool":
                if on_output:
                    on_output(Text("⚠ Batas langkah tercapai — menyusun ringkasan akhir...", style="dim yellow"))
                if on_status:
                    on_status("thinking", f"🧠 Menyusun laporan akhir ({self.spec.name})...")
                try:
                    streamed_chunks = []
                    synthesis_content, _ = self.provider.chat(
                        messages=self.messages + [{
                            "role": "user",
                            "content": "Batas langkah tercapai. Sintesiskan semua temuan di atas dan berikan laporan audit/ringkasan lengkap sekarang."
                        }],
                        tools=[],
                        on_chunk=on_chunk,
                    )
                    if synthesis_content:
                        clean_syn = strip_reasoning(synthesis_content).strip()
                        if not streamed_chunks:
                            if clean_syn:
                                if on_output:
                                    on_output(Markdown(clean_syn))
                                else:
                                    print_markdown(clean_syn)
                        final_response += clean_syn
                        self.messages.append({"role": "assistant", "content": clean_syn})
                except Exception:
                    pass

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚡ Operation interrupted by user (Ctrl+C).[/bold yellow]")
            # The work done before the interrupt is still real; persist it so a
            # Ctrl+C followed by /exit does not throw the turn away.
            if not ephemeral:
                self._save_quietly()
            return final_response

        if ephemeral:
            # Revert history and counters if run in side-question mode (/btw)
            self.rewind_checkpoint()
            (self.turns_count, self.total_input_tokens,
             self.total_output_tokens, self.last_input_tokens) = counters_before
        else:
            self._save_quietly()

            # Edits were made, so check the project still builds/tests clean.
            # Runs only once the turn settled, never mid-loop.
            if not self.cancel_requested.is_set():
                self._auto_verify(on_output)

        # Turn completion status line matching Claude Code (* Worked for Xs · done HH:MM PM)
        elapsed = time.time() - turn_start_time
        import datetime
        now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
        summary_str = f"* Worked for {elapsed:.1f}s · done {now_str}"
        if on_output:
            on_output(Text(f"\n{summary_str}\n", style="dim"))
        else:
            console.print(f"\n[dim]{summary_str}[/dim]\n")

        if self.advisor_model and final_response and not ephemeral:
            self._run_advisor(final_response, on_output)

        # Audio completion alert if turn was longer than 8 seconds
        if elapsed > 8.0 and self.notify_completion:
            import sys
            sys.stdout.write("\a")
            sys.stdout.flush()

        return final_response
