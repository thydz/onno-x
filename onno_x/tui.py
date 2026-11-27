import difflib
import inspect
import math
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.markup import escape as _escape_markup

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static, TextArea
from textual.widgets.option_list import Option
from textual.widgets.text_area import Selection

from onno_x.mentions import human_size, iter_mentions


class SelectableAnswer(TextArea):
    """Selectable response with native Textual mouse selection and macOS clipboard."""

    def __init__(self, content: str = "") -> None:
        super().__init__(content, read_only=True, show_line_numbers=False,
                         soft_wrap=True, theme="css")
        self._answer = content

    def on_mount(self) -> None:
        self._fit_height()

    def on_resize(self, event) -> None:
        self._fit_height()

    def _fit_height(self) -> None:
        # Expand to show response, leaving wheel scrolling to conversation log.
        import shutil
        width = max(20, getattr(self.size, "width", 0) or shutil.get_terminal_size().columns - 6)
        estimated = sum(max(1, (len(line) + width - 1) // width)
                        for line in self._answer.split("\n"))
        self.styles.height = max(2, estimated + 2)

    def set_answer(self, content: str) -> None:
        # Streaming replaces the document every ~35ms. load_text() resets the
        # selection, so preserve it while the user is dragging or has text
        # selected; otherwise a copy attempt during streaming silently dies.
        previous = self.selection
        keep_selection = self._selecting or previous.start != previous.end
        self._answer = content
        self.load_text(content)
        if keep_selection:
            self.selection = Selection(previous.start, previous.end)
        self._fit_height()

    def on_mouse_up(self, event) -> None:
        selected = self.selected_text
        if not selected:
            return
        ok = self.app.copy_text_to_clipboard(selected)
        update = getattr(self.app, "update_status", None)
        if callable(update):
            if ok:
                update(f"✔ Copied selection ({len(selected)} chars) to clipboard")
            else:
                update("⚠ No clipboard tool found — selection saved to ~/.onno-x/last_response.txt")



class ConversationLog(VerticalScroll):
    """Scrollable container for conversation messages supporting live streaming and rich widgets."""

    def write(self, renderable: Any) -> Widget:
        if isinstance(renderable, Widget):
            w = renderable
        elif isinstance(renderable, str):
            # Raw strings may contain brackets (e.g. tool output) that Rich
            # would misread as markup tags; render them as plain text.
            w = Static(Text(renderable))
        else:
            w = Static(renderable)
        self.mount(w)
        self.scroll_end(animate=False)
        return w

    def clear(self) -> None:
        self.remove_children()

from onno_x.config import load_config, save_config, CONFIG_DIR
from onno_x.main import (
    SLASH_COMMANDS,
    PasteFoldingInput,
    expand_at_file_mentions,
    expand_pasted_blocks,
)
from onno_x.session import AgentSession, strip_reasoning
from onno_x.commands import (
    detect_lint_command,
    detect_test_command,
    expand_alias,
    find_command_help,
    find_files,
    git_log,
    git_stash,
    grep_repo,
    run_shell_capture,
    token_breakdown,
)
from onno_x.tools import execute_tool, get_active_tool_definitions
from onno_x.ui import (
    GRADIENTS,
    gradient_text,
    print_tool_call,
    print_tool_result,
    resolve_accent,
)


# Terminal UI Animation Frames
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
PROGRESS_PULSE = [
    "[■□□□□□□□□□]",
    "[■■□□□□□□□□]",
    "[■■■□□□□□□□]",
    "[□■■■□□□□□□]",
    "[□□■■■□□□□□]",
    "[□□□■■■□□□□]",
    "[□□□□■■■□□□]",
    "[□□□□□■■■□□]",
    "[□□□□□□■■■□]",
    "[□□□□□□□■■■]",
    "[□□□□□□□□■■]",
    "[□□□□□□□□□■]",
]

# Lebar maskot (dalam kolom) untuk animasi banner
MASCOT_WIDTH = 9

# Siklus kaki 4 frame membuat langkah terasa lebih halus dari 2 frame.
WALK_LEGS = ["  ▘▘ ▝▝  ", "  ▘▝ ▝▘  ", "  ▝▝ ▘▘  ", "  ▝▘ ▘▝  "]
TAP_LEGS = ["  ▘▘ ▝▝  ", "  ▘▘▝▝   "]
THINK_BUBBLES = ["hmm", "hmm.", "hmm..", "hmm...", "eh?", "aha!"]


class OnnoXUI(App):
    """Terminal UI inspired by Claude Code CLI built on Textual."""

    CSS = """
    Screen {
        background: #141414;
        color: #e0e0e0;
        overflow: hidden;
    }

    #banner {
        dock: top;
        height: auto;
        min-height: 5;
        max-height: 5;
        width: 100%;
        padding: 0 1;
        background: #141414;
    }

    #conversation {
        height: 1fr;
        padding: 0 1;
        background: #141414;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #bottom {
        dock: bottom;
        height: auto;
        width: 100%;
        background: #141414;
    }

    SelectableAnswer {
        width: 100%;
        border: none;
        background: #141414;
        color: #e0e0e0;
        padding: 0;
    }

    #autocomplete-list {
        max-height: 8;
        width: 100%;
        background: #1a1a22;
        border: solid #2e2e38;
        color: #ffffff;
        display: none;
    }

    #divider-top {
        height: 1;
        color: #383838;
    }

    #input-row {
        height: 1;
        width: 100%;
        background: #141414;
    }

    #prompt-symbol {
        width: 2;
        height: 1;
        color: #ffffff;
        text-style: bold;
    }

    #prompt {
        width: 1fr;
        height: 1;
        border: none;
        padding: 0;
        background: #141414;
        color: #ffffff;
    }

    #divider-bottom {
        height: 1;
        color: #383838;
    }

    #status {
        height: 1;
        padding-left: 0;
        background: #141414;
    }
    """

    BINDINGS = [
        Binding("shift+tab", "cycle_permission_mode", "Cycle Permission Mode", priority=True),
        Binding("escape", "interrupt_or_clear", "Interrupt / Clear", priority=True),
        Binding("ctrl+c", "cancel_turn", "Cancel Turn / Copy Selection", priority=True),
        Binding("ctrl+shift+c", "copy_selection", "Copy Selection", priority=True),
        Binding("ctrl+y", "copy_last_response", "Copy Last Response", priority=True),
        Binding("pageup", "scroll_page_up", "Scroll Up", priority=True),
        Binding("pagedown", "scroll_page_down", "Scroll Down", priority=True),
    ]

    def __init__(
        self,
        active_model: Optional[str] = None,
        version: str = "",
        on_submit: Optional[Callable] = None,
        session: Optional[AgentSession] = None,
    ):
        super().__init__()
        self.cfg = load_config()
        if active_model and active_model in self.cfg.models:
            self.cfg.active_model = active_model
        self.active_model = self.cfg.active_model
        if not version:
            from onno_x import __version__

            version = f"v{__version__}"
        self.version = version
        self.session = session or AgentSession(self.cfg)
        self.on_submit = on_submit
        self.is_running_turn = False
        self._pending_cancel = False
        self._esc_press_time = 0.0
        self.last_response: str = ""
        self.pending_permission: Optional[Dict[str, Any]] = None

        # Live activity ticker & spinner animation state
        self.activity_kind: str = "idle"
        self.activity_detail: str = ""
        self._turn_start_time: float = 0.0
        self._spinner_idx: int = 0
        self._activity_timer = None

        # Banner walking mascot state
        self._banner_offset: float = 0.0  # posisi pecahan -> gerak halus
        self._banner_phase: float = 0.0  # 0..1, gerak sinusoidal bolak-balik
        self._banner_step: int = 0
        self._banner_track: int = 24
        self._banner_timer = None
        self._banner_frame: int = 0
        self._banner_mode_cur: str = "walk"  # walk | think | write

        # Input command history tracking (Up/Down arrow navigation)
        self.input_history: List[str] = []
        self.history_index: int = -1
        self.history_stash: str = ""
        self.load_history()

        # Wire up non-blocking permission handler
        self.session.permission_handler = self.request_permission_from_worker

    def load_history(self):
        """Load persistent command history from history.txt."""
        h_file = CONFIG_DIR / "history.txt"
        if h_file.exists():
            try:
                for line in h_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line.startswith("+"):
                        cmd = line[1:].strip()
                        if cmd and (not self.input_history or self.input_history[-1] != cmd):
                            self.input_history.append(cmd)
            except Exception:
                pass

    def save_to_history(self, cmd: str):
        """Append submitted command to persistent history file."""
        from datetime import datetime
        h_file = CONFIG_DIR / "history.txt"
        try:
            h_file.parent.mkdir(parents=True, exist_ok=True)
            with open(h_file, "a", encoding="utf-8") as f:
                f.write(f"\n# {datetime.now()}\n+{cmd}\n")
        except Exception:
            pass

    def history_up(self):
        """Navigate backwards into previous command history (Up arrow)."""
        if not self.input_history:
            return
        inp = self.query_one("#prompt", Input)
        if self.history_index == -1:
            self.history_stash = inp.value
        if self.history_index + 1 < len(self.input_history):
            self.history_index += 1
            entry = self.input_history[-(self.history_index + 1)]
            inp.value = entry
            inp.cursor_position = len(entry)

    def history_down(self):
        """Navigate forwards towards recent command history (Down arrow)."""
        if not self.input_history:
            return
        inp = self.query_one("#prompt", Input)
        if self.history_index > 0:
            self.history_index -= 1
            entry = self.input_history[-(self.history_index + 1)]
            inp.value = entry
            inp.cursor_position = len(entry)
        elif self.history_index == 0:
            self.history_index = -1
            inp.value = self.history_stash
            inp.cursor_position = len(inp.value)

    # ==========================================
    # LAYOUT
    # ==========================================

    def compose(self) -> ComposeResult:
        yield Static(self.create_banner(), id="banner")
        yield ConversationLog(id="conversation")
        with Vertical(id="bottom"):
            yield OptionList(id="autocomplete-list")
            yield Static("─" * 300, id="divider-top")
            with Horizontal(id="input-row"):
                yield Static("❯ ", id="prompt-symbol")
                yield PasteFoldingInput(
                    placeholder='Try "fix lint errors" or "explain code"...',
                    id="prompt",
                )
            yield Static("─" * 300, id="divider-bottom")
            yield Static(self.get_status_text(), id="status")

    def on_mount(self):
        """Focus input when application starts and render restored session if present."""
        conv = self.query_one("#conversation", ConversationLog)
        conv.can_focus = True
        self.query_one("#prompt", Input).focus()
        # Animasi maskot berjalan di banner
        # ~14 fps: cukup halus untuk mata, masih murah untuk render ulang.
        self._banner_timer = self.set_interval(0.07, self._tick_banner)
        if len(self.session.messages) > 1:
            self.render_resumed_session_log()

    def render_resumed_session_log(self):
        """Render restored messages from a resumed session into conversation log."""
        log = self.get_log()
        log.write(Text(f"🔄 Sesi Dimuat: {self.session.session_id} ({len(self.session.messages)} riwayat pesan)", style="bold cyan"))
        log.write(Text("─" * 80, style="dim"))
        for msg in self.session.messages[1:]:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" and content:
                # If content has attachments, extract clean prompt
                clean_c = content.split("\n\n--- [Attachment:")[0].strip()
                self.print_user_prompt_bar(clean_c)
            elif role == "assistant" and content:
                self.print_markdown(content)
            elif role == "tool" and content:
                snippet = content.strip()
                if len(snippet) > 300:
                    snippet = snippet[:300] + "\n... (truncated)"
                tool_name = msg.get("name", "tool")
                log.write(Panel(Text(snippet), border_style="dim white", title=f"Output Tool: {tool_name}", title_align="left"))
        log.write(Text("\n✔ Riwayat sesi siap dilanjutkan.\n", style="dim green"))

    def on_click(self, event) -> None:
        """Refocus prompt on click, unless clicking conversation area (allow scroll)."""
        popup = self.query_one("#autocomplete-list", OptionList)
        # Don't steal focus if click is inside conversation log — let mouse wheel scroll work
        widget = event.widget
        while widget is not None:
            if isinstance(widget, (ConversationLog, SelectableAnswer)):
                return
            widget = getattr(widget, "parent", None)
        if not popup.display:
            try:
                self.query_one("#prompt", Input).focus()
            except Exception:
                pass

    # ==========================================
    # BANNER
    # ==========================================

    def create_banner(self) -> Panel:
        cwd = str(Path.cwd())
        home = str(Path.home())
        if cwd == home:
            display_cwd = "~"
        elif cwd.startswith(home):
            display_cwd = "~" + cwd[len(home):]
        else:
            display_cwd = cwd

        # Responsive layout: adapt to terminal width
        width = self.size.width if hasattr(self, "size") and self.size.width else 80
        if width < 60 and len(display_cwd) > width - 15:
            display_cwd = "..." + display_cwd[-(width - 18):]

        sid = getattr(self.session, "session_id", "default")
        if len(sid) > 12 and width < 70:
            sid = sid[:10] + "…"

        # --- Info (statis, kanan) ---
        accent = resolve_accent(getattr(self.cfg, "accent_color", None))
        start, end = GRADIENTS.get(accent, GRADIENTS["cyan"])

        info = Text()
        # Baris 1: wordmark bergradient + badge versi
        info.append_text(gradient_text("Onno-X", start, end))
        info.append(f"  v{str(self.version).lstrip('v')}", style=f"bold {end}")
        info.append("  coding agent\n", style="dim")
        # Baris 2: Model aktif dan Session ID
        info.append("◆ ", style=f"bold {start}")
        info.append(f"{self.active_model}", style="bold white")
        info.append("  ◆ ", style=f"bold {end}")
        info.append(f"{sid}\n", style="dim green")
        # Baris 3: Path folder aktif
        info.append("◆ ", style=f"bold {end}")
        info.append(display_cwd, style="dim")

        # --- Lebar lintasan maskot menyesuaikan lebar terminal ---
        info_w = max(len(line) for line in info.plain.split("\n"))
        # 2 (padding banner) + 2 (border) + 2 (padding panel) + 2 (jarak kolom)
        track_w = width - info_w - 8
        track_w = max(MASCOT_WIDTH, min(24, track_w))
        self._banner_track = track_w

        # Terminal sempit: potong baris info agar bingkai kanan tetap rapi.
        avail = width - track_w - 7
        if avail >= 12 and info_w > avail:
            trimmed = Text()
            for idx, line in enumerate(info.split("\n")):
                part = line.copy()
                part.truncate(avail, overflow="ellipsis")
                trimmed.append_text(part)
                if idx < 2:
                    trimmed.append("\n")
            info = trimmed

        # --- Maskot: animasi tergantung mode (walk / think / write) ---
        mode = self._banner_mode_cur
        frame = self._banner_frame
        color = "#cc785c"
        effects: list = []  # (baris, teks, style) di samping maskot

        if mode == "think":
            # Mengetuk kaki pelan + gelembung pikiran yang tumbuh/menyusut
            legs = TAP_LEGS[(frame // 6) % len(TAP_LEGS)]
            bubble = THINK_BUBBLES[(frame // 7) % len(THINK_BUBBLES)]
            effects = [
                (0, "˙", f"dim {end}"),
                (1, f"○ {bubble}", f"italic {end}"),
            ]
            color = ["#cc785c", "#e5a469"][(frame // 5) % 2]
        elif mode == "write":
            # Pena menulis baris yang tumbuh, lalu "selesai" sekejap
            legs = WALK_LEGS[frame % 2]
            ink = (frame % 16) // 2
            stroke = "▁" * min(ink, 7)
            effects = [(1, f"✎ {stroke}".rstrip(), "bold #7ec699" if ink % 2 else "#7ec699")]
            if ink >= 6:
                effects.append((0, "✓", "bold #7ec699"))
            color = "#e5a469"
        else:
            # Berjalan (membaca / menjalankan tool / idle)
            legs = WALK_LEGS[(self._banner_step // 2) % len(WALK_LEGS)]
            if frame % 9 < 3:
                effects = [(2, "·", f"dim {start}")]

        art = [" ▐▛███▜▌ ", "▝▜█████▛▘", legs]
        off = int(round(min(self._banner_offset, track_w - MASCOT_WIDTH)))
        body_style = f"bold {color}"
        fits_right = all(
            off + MASCOT_WIDTH + 2 + len(text) <= track_w for _, text, _ in effects
        )
        fits_left = all(off >= len(text) + 2 for _, text, _ in effects)

        walker = Text()
        for i, line in enumerate(art):
            row_effects = [(text, style) for row, text, style in effects if row == i]
            row = Text()
            if row_effects and not fits_right and fits_left:
                label = " ".join(text for text, _ in row_effects)
                row.append(" " * (off - len(label) - 1))
                row.append(label, style=row_effects[0][1])
                row.append(" ")
            else:
                row.append(" " * off)
            row.append(line, style=body_style)
            if row_effects and fits_right:
                row.append(" " + " ".join(text for text, _ in row_effects), style=row_effects[0][1])
            pad = track_w - row.cell_len
            if pad > 0:
                row.append(" " * pad)
            walker.append_text(row)
            if i < len(art) - 1:
                walker.append("\n")

        grid = Table.grid(padding=(0, 2))
        grid.add_column(no_wrap=True, width=track_w, vertical="middle")
        grid.add_column(vertical="middle")
        grid.add_row(walker, info)

        # Bingkai statis, hanya isi (maskot) yang bergerak
        return Panel(
            grid,
            box=box.ROUNDED,
            border_style=accent,
            padding=(0, 1),
            expand=True,
            subtitle=" onno-x " if width >= 80 else None,
            subtitle_align="right",
        )

    def _banner_mode(self) -> str:
        """Tentukan mode animasi maskot dari status aktivitas agent.

        - think : model sedang reasoning  -> maskot diam + gelembung pikiran
        - write : model sedang menulis    -> maskot diam + pena menulis
        - walk  : membaca / tool berjalan / idle -> maskot berjalan
        """
        if not getattr(self, "is_running_turn", False):
            return "walk"
        kind = getattr(self, "activity_kind", "idle")
        if kind == "thinking":
            return "think"
        if kind in ("generating", "writing"):
            return "write"
        return "walk"

    def _tick_banner(self):
        """Animasi maskot di dalam bingkai (bingkai tetap diam)."""
        self._banner_frame += 1
        mode = self._banner_mode()
        self._banner_mode_cur = mode

        if mode == "walk":
            max_off = max(0, self._banner_track - MASCOT_WIDTH)
            # Gerak sinusoidal: pelan di ujung, cepat di tengah, tanpa hentakan
            # saat berbalik — jauh lebih halus daripada langkah +1/-1.
            # Putaran penuh ~5,6 dtk (80 tick x 0,07 dtk) agar lintasan 15 sel
            # tetap terasa berjalan, bukan merayap.
            self._banner_phase = (self._banner_phase + 0.0125) % 1.0
            wave = 0.5 - 0.5 * math.cos(2 * math.pi * self._banner_phase)
            self._banner_offset = max_off * wave
            self._banner_step = int(self._banner_phase * 128)

        # Mode think/write: posisi tidak berubah, hanya frame animasinya
        try:
            self.update_banner()
        except Exception:
            pass

    def on_resize(self, event) -> None:
        """Dynamically update banner on terminal window resize."""
        try:
            self.update_banner()
        except Exception:
            pass

    def update_banner(self):
        banner_widget = self.query_one("#banner", Static)
        banner_widget.update(self.create_banner())

    # ==========================================
    # STATUS BAR
    # ==========================================

    def get_status_text(self) -> Text:
        mode = getattr(self.session, "permission_mode", "auto").lower()
        plan = " [PLAN]" if getattr(self.session, "plan_mode", False) else ""
        t = Text()
        t.append(f"▶▶ {mode} mode on{plan} ", style="bold #e5a469")
        t.append("· shift+tab mode · ctrl+y copy · esc stop", style="dim #888888")
        return t

    def update_status(self, custom_text: Optional[Any] = None):
        status_widget = self.query_one("#status", Static)
        if custom_text is None:
            status_widget.update(self.get_status_text())
        elif isinstance(custom_text, (Text, Table, Panel)):
            status_widget.update(custom_text)
        else:
            status_widget.update(Text(str(custom_text)))

    def start_activity_ticker(self, initial_detail: str = "🧠 Membaca konteks & berpikir..."):
        """Start a 100ms interval timer that animates spinner, progress pulse, and elapsed timer."""
        self.activity_kind = "reading"
        self.activity_detail = initial_detail
        self._turn_start_time = time.time()
        self._spinner_idx = 0
        if getattr(self, "_activity_timer", None):
            try:
                self._activity_timer.stop()
            except Exception:
                pass
        self._activity_timer = self.set_interval(0.12, self._tick_activity_status)

    def stop_activity_ticker(self):
        """Stop the background activity animation timer."""
        self.activity_kind = "idle"
        if getattr(self, "_activity_timer", None):
            try:
                self._activity_timer.stop()
            except Exception:
                pass
            self._activity_timer = None

    def _tick_activity_status(self):
        """Periodic callback running every 120ms to render the live activity status bar."""
        if not getattr(self, "is_running_turn", False):
            return
        self._spinner_idx += 1
        spin = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
        pulse = PROGRESS_PULSE[self._spinner_idx % len(PROGRESS_PULSE)]
        elapsed = time.time() - getattr(self, "_turn_start_time", time.time())

        t = Text()
        t.append(f"{spin} ", style="bold cyan")
        t.append(f"{pulse} ", style="bold #e5a469")
        detail = getattr(self, "activity_detail", "Bekerja...")
        t.append(f"{detail} ", style="bold white")
        t.append(f"({elapsed:.1f}s) ", style="bold yellow")
        t.append("· esc to interrupt", style="dim #888888")

        try:
            status_widget = self.query_one("#status", Static)
            status_widget.update(t)
        except Exception:
            pass

    # ==========================================
    # KEY ACTIONS & EVENT HANDLERS
    # ==========================================

    def action_cycle_permission_mode(self):
        order = ["auto", "manual", "all"]
        cur = getattr(self.session, "permission_mode", "auto").lower()
        idx = order.index(cur) if cur in order else 0
        new_mode = order[(idx + 1) % len(order)]
        self.session.permission_mode = new_mode
        self.update_status()

    def action_cancel_turn(self):
        """Cancel the running turn immediately (Ctrl+C)."""
        if self.pending_permission:
            self.pending_permission["choice"] = "n"
            self.pending_permission["event"].set()
            return
        if self.is_running_turn:
            if hasattr(self.session, "cancel_requested"):
                self.session.cancel_requested.set()
            self._pending_cancel = False
            self.update_status("⚡ Interrupting current turn...")
            return
        # TextArea's own Ctrl+C copy binding never fires because this App binding
        # has priority. When idle, make Ctrl+C copy the current selection too.
        focused = self.focused
        if focused and getattr(focused, "selected_text", ""):
            self.action_copy_selection()

    def action_copy_selection(self):
        """Copy the focused widget's selected text, falling back to last response."""
        focused = self.focused
        selected = getattr(focused, "selected_text", "") if focused else ""
        if selected:
            ok = self.copy_text_to_clipboard(selected)
            if ok:
                self.update_status(f"✔ Copied selection ({len(selected)} chars) to clipboard")
            else:
                self.update_status("⚠ No clipboard tool found — selection saved to ~/.onno-x/last_response.txt")
            return
        self.action_copy_last_response()

    def action_interrupt_or_clear(self):
        # If permission prompt is pending, Esc cancels permission
        if self.pending_permission:
            self.pending_permission["choice"] = "n"
            self.pending_permission["event"].set()
            return

        # If autocomplete popup is open, close it
        popup = self.query_one("#autocomplete-list", OptionList)
        if popup.display:
            popup.display = False
            return

        # If a turn is running, require a second Esc within 1.5s to cancel.
        # This prevents stray terminal escape sequences from aborting a turn.
        if self.is_running_turn:
            import time as _t
            now = _t.monotonic()
            if self._pending_cancel and (now - self._esc_press_time) < 1.5:
                self._pending_cancel = False
                if hasattr(self.session, "cancel_requested"):
                    self.session.cancel_requested.set()
                self.update_status("⚡ Interrupting current turn...")
                return
            self._esc_press_time = now
            self._pending_cancel = True
            self.update_status("Tekan ESC lagi (atau Ctrl+C) untuk membatalkan turn")
            return

        inp = self.query_one("#prompt", Input)
        if inp.value:
            inp.value = ""
        else:
            self.update_status("⚡ Esc pressed")

    def copy_text_to_clipboard(self, text: str) -> bool:
        """Helper to copy text to system clipboard (macOS, Linux, Termux) and save to disk."""
        if not text:
            return False
        import subprocess
        success = False
        # 1. macOS pbcopy
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            p.communicate(text.encode("utf-8"))
            if p.returncode == 0:
                success = True
        except Exception:
            pass

        # 2. Android Termux
        if not success:
            try:
                p = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                p.communicate(text.encode("utf-8"))
                if p.returncode == 0:
                    success = True
            except Exception:
                pass

        # 3. Linux X11 (xclip)
        if not success:
            try:
                p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                p.communicate(text.encode("utf-8"))
                if p.returncode == 0:
                    success = True
            except Exception:
                pass

        # 4. Linux Wayland (wl-copy)
        if not success:
            try:
                p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                p.communicate(text.encode("utf-8"))
                if p.returncode == 0:
                    success = True
            except Exception:
                pass

        # Also persist to file for easy terminal access via: cat ~/.onno-x/last_response.txt
        try:
            out_file = CONFIG_DIR / "last_response.txt"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(text, encoding="utf-8")
        except Exception:
            pass

        return success

    def get_latest_response_text(self) -> str:
        """Get the latest assistant response, or tool output, or last message content."""
        if self.last_response and self.last_response.strip():
            return self.last_response.strip()

        if self.session and self.session.messages:
            for m in reversed(self.session.messages):
                c = m.get("content")
                if c and isinstance(c, str) and c.strip():
                    return c.strip()

        # Check saved file fallback
        out_file = CONFIG_DIR / "last_response.txt"
        if out_file.exists():
            try:
                return out_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return ""

    def action_copy_last_response(self):
        """Copy the latest AI response to macOS clipboard (Ctrl+Y)."""
        target = self.get_latest_response_text()
        if target:
            self.copy_text_to_clipboard(target)
            self.update_status(f"✔ Copied last response ({len(target)} chars) to clipboard! (Ctrl+Y)")
        else:
            self.update_status("⚠ No response to copy yet")

    def action_scroll_page_up(self):
        """Scroll the conversation log up one page."""
        try:
            self.query_one("#conversation", ConversationLog).scroll_page_up()
        except Exception:
            pass

    def action_scroll_page_down(self):
        """Scroll the conversation log down one page."""
        try:
            self.query_one("#conversation", ConversationLog).scroll_page_down()
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed):
        """Handle permission shortcuts and slash command autocomplete popup."""
        # 1. If permission prompt is pending, single key 'y', 'n', or 'a' resolves it immediately
        if self.pending_permission:
            val = event.value.strip().lower()
            if val in ("y", "n", "a"):
                self.pending_permission["choice"] = val
                self.pending_permission["event"].set()
                event.input.value = ""
                return

        # 2. Autocomplete popup matching Image 3
        popup = self.query_one("#autocomplete-list", OptionList)
        val = event.value
        if val.startswith("/") and " " not in val:
            popup.clear_options()
            matching = [
                (cmd, desc)
                for cmd, desc in SLASH_COMMANDS
                if cmd.lower().startswith(val.lower())
            ]
            if matching:
                for cmd, desc in matching:
                    # Format matching Claude Code CLI autocompletion: cmd (width 16) + description
                    clean_desc = desc[:75] + ("..." if len(desc) > 75 else "")
                    label = f"{cmd:<16}  {clean_desc}"
                    popup.add_option(Option(label, id=cmd))
                popup.display = True
                popup.highlighted = 0
            else:
                popup.display = False
            self._mention_mode = False
        else:
            # Picker `@file` / `@folder`: token terakhir diawali '@'.
            self._mention_mode = False
            popup.display = False
            tokens = val.split()
            token = tokens[-1] if tokens else ""
            if val and token.startswith("@"):
                prefix = token[1:]
                start = val.rfind("@")
                entries = iter_mentions(Path.cwd(), prefix)
                if entries:
                    popup.clear_options()
                    for rel, is_dir, size in entries:
                        value = rel + "/" if is_dir else rel
                        meta = "DIR" if is_dir else human_size(size)
                        popup.add_option(Option(f"{value:<44}  {meta}", id=value))
                    popup.display = True
                    popup.highlighted = 0
                    self._mention_mode = True
                    self._mention_start = start
                    self._mention_end = len(val)

    def on_key(self, event: Key):
        """Route keys for permission prompt and autocomplete navigation."""
        # 1. Handle pending tool permission prompt (Single-key press without Enter required)
        if self.pending_permission:
            k = event.key.lower()
            if k in ("y", "enter"):
                self.pending_permission["choice"] = "y"
                self.pending_permission["event"].set()
                event.stop()
                event.prevent_default()
                return
            elif k in ("n", "escape"):
                self.pending_permission["choice"] = "n"
                self.pending_permission["event"].set()
                event.stop()
                event.prevent_default()
                return
            elif k == "a":
                self.pending_permission["choice"] = "a"
                self.pending_permission["event"].set()
                event.stop()
                event.prevent_default()
                return

        # 2. Handle autocomplete popup navigation
        popup = self.query_one("#autocomplete-list", OptionList)
        inp = self.query_one("#prompt", Input)
        if popup.display:
            if event.key == "down":
                popup.action_cursor_down()
                event.stop()
                event.prevent_default()
                return
            elif event.key == "up":
                popup.action_cursor_up()
                event.stop()
                event.prevent_default()
                return
            elif event.key in ("tab", "enter") and popup.highlighted is not None:
                opt = popup.get_option_at_index(popup.highlighted)
                if opt:
                    if getattr(self, "_mention_mode", False):
                        value = str(opt.id)
                        start = getattr(self, "_mention_start", 0)
                        end = getattr(self, "_mention_end", len(inp.value))
                        before = inp.value[:start]
                        after = inp.value[end:]
                        inserted = "@" + value
                        if value.endswith("/"):
                            # Folder: biarkan kursor di dalamnya agar bisa lanjut menelusuri.
                            inp.value = before + inserted + after
                            inp.cursor_position = len(before) + len(inserted)
                        else:
                            if not after.startswith(" "):
                                inserted += " "
                            inp.value = before + inserted + after
                            inp.cursor_position = len(before) + len(inserted)
                        self._mention_mode = False
                    else:
                        inp.value = str(opt.id) + " "
                        inp.cursor_position = len(inp.value)
                    popup.display = False
                    event.stop()
                    event.prevent_default()
                    return
            elif event.key == "escape":
                popup.display = False
                event.stop()
                event.prevent_default()
                return
        else:
            # 3. Ensure input has focus if user starts typing when autocomplete is not open
            if self.focused != inp and event.key not in ("up", "down", "shift+tab", "ctrl+y", "escape"):
                inp.focus()

            # 4. When autocomplete popup is not open, Up and Down navigate command history
            if event.key == "up":
                self.history_up()
                event.stop()
                event.prevent_default()
                return
            elif event.key == "down":
                self.history_down()
                event.stop()
                event.prevent_default()
                return

    def safe_call_from_thread(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        """Call method from worker thread safely, guarding against shutdown race."""
        if self.is_running:
            try:
                self.call_from_thread(fn, *args, **kwargs)
            except Exception:
                pass

    # ==========================================
    # PERMISSION PROMPT HANDLER (NEVER FREEZES)
    # ==========================================

    def request_permission_from_worker(
        self, name: str, args: dict, effective_mode: str
    ) -> str:
        """Called from agent background worker thread. Prompts user with 60s timeout."""
        evt = threading.Event()
        self.pending_permission = {
            "name": name,
            "args": args,
            "event": evt,
            "choice": "n",
        }

        # Format details into conversation log
        prompt_panel = Table.grid(padding=(0, 1))
        prompt_panel.add_column(ratio=1)

        summary_line = f"⚡ Tool Permission Request ({effective_mode.upper()} mode):"
        if name == "run_shell":
            detail = f"Command: {args.get('command')}"
        elif name in ("write_file", "edit_file"):
            detail = f"Action: {name} on {args.get('path')}"
        elif name == "delete_file":
            detail = f"Action: Delete {args.get('path')}"
        else:
            detail = f"Action: {name} ({args})"
        # Tool args are untrusted input and may contain Rich markup-like
        # brackets; escape them so the permission panel renders safely.
        detail = _escape_markup(str(detail))
        summary_line = _escape_markup(str(summary_line))

        self.safe_call_from_thread(
            self.get_log().write,
            Panel(
                f"[bold yellow]{summary_line}[/bold yellow]\n[bold cyan]{detail}[/bold cyan]\n"
                f"Allow execution? [bold green][y]yes[/bold green] / [bold red][n]no[/bold red] / [bold yellow][a]ccept all for session[/bold yellow] (Enter=yes, 60s timeout)",
                border_style="yellow",
                title="Permission Required",
                title_align="left",
            ),
        )

        status_text = Text()
        status_text.append(f"⚡ Allow '{name}'? ", style="bold yellow")
        status_text.append("y=yes · n=no · a=always · esc=cancel", style="bold white")
        self.safe_call_from_thread(self.update_status, status_text)

        def set_perm_ui():
            inp = self.query_one("#prompt", Input)
            inp.placeholder = "Press [y]es / [n]o / [a]ccept all (Enter=yes)..."
            inp.value = ""

        def reset_perm_ui():
            inp = self.query_one("#prompt", Input)
            inp.placeholder = 'Try "fix lint errors" or "explain code"...'
            inp.value = ""

        self.safe_call_from_thread(set_perm_ui)

        # Wait with 60s safety timeout to PREVENT ANY FREEZE OR LOCKUP
        got_response = evt.wait(timeout=60.0)

        if not got_response:
            choice = "n"
            self.safe_call_from_thread(
                self.print_markdown,
                "[yellow]⚡ Permission request timed out after 60s (auto-denied).[/yellow]",
            )
        else:
            choice = self.pending_permission["choice"]

        if choice in ("a", "all"):
            self.session.permission_mode = "all"
            self.safe_call_from_thread(
                self.print_markdown,
                "[bold green]✔ Switched to ACCEPT ALL mode for this session.[/bold green]",
            )

        self.pending_permission = None
        self.safe_call_from_thread(reset_perm_ui)
        self.safe_call_from_thread(self.update_status)
        return choice

    # ==========================================
    # OUTPUT HANDLERS (LOG DISPLAY)
    # ==========================================

    def get_log(self) -> ConversationLog:
        return self.query_one("#conversation", ConversationLog)

    def print_markdown(self, content: str):
        self.get_log().write(SelectableAnswer(content))

    def print_user_prompt_bar(self, text: str):
        clean_text = text.replace("\n", " ").strip()
        bar = Table.grid(expand=True, padding=(0, 1))
        bar.add_column(ratio=1)
        bar.add_row(Text(f"❯ {clean_text}", style="bold white"))
        bar.style = "on #24242e"
        self.get_log().write(bar)

    def print_slash_result(self, cmd: str, result_desc: str):
        self.get_log().write(
            Text.assemble(
                ("❯ ", "bold white"),
                (f"{cmd}\n", "bold cyan"),
                ("  └ ", "dim"),
                (f"{result_desc}", "white"),
            )
        )

    def print_tool_call(self, name: str, args: dict):
        self.get_log().write(
            Text.assemble(
                ("⚙ Executing tool: ", "bold yellow"),
                (name, "bold green"),
                (f" {args}", "dim"),
            )
        )

    def print_tool_result(self, result: str, error: bool = False):
        color = "red" if error else "dim white"
        snippet = result.strip()
        if len(snippet) > 800:
            snippet = snippet[:800] + "\n... (truncated)"
        self.get_log().write(
            Panel(
                Text(snippet),
                border_style=color,
                title="Tool Output",
                title_align="left",
            )
        )

    def print_models_table(self, models: dict, active: str):
        table = Table(title="Configured Models (onno-x)", border_style="cyan")
        table.add_column("Active", justify="center", style="bold green", width=8)
        table.add_column("Alias", style="bold yellow")
        table.add_column("Provider", style="magenta")
        table.add_column("Model ID", style="white")
        table.add_column("Base URL", style="dim cyan")
        for alias, spec in models.items():
            is_active = "✔" if alias == active else ""
            table.add_row(
                is_active,
                alias,
                spec.provider,
                spec.model_id,
                spec.base_url or "(default)",
            )
        self.get_log().write(table)

    def print_help_table(self):
        table = Table(title="Slash Commands", border_style="cyan")
        table.add_column("Command", style="bold cyan", width=18)
        table.add_column("Deskripsi", style="white")
        for cmd, desc in SLASH_COMMANDS:
            table.add_row(cmd, desc)
        self.get_log().write(table)

    # ==========================================
    # USER INPUT SUBMISSION & WORKER
    # ==========================================

    async def on_input_submitted(self, event: Input.Submitted):
        # Hide autocomplete popup if open
        popup = self.query_one("#autocomplete-list", OptionList)
        popup.display = False

        raw_message = event.value.strip()

        # If a tool permission prompt is pending, Enter defaults to 'y'
        if self.pending_permission:
            choice = raw_message.lower() if raw_message in ("y", "n", "a") else "y"
            self.pending_permission["choice"] = choice
            self.pending_permission["event"].set()
            event.input.value = ""
            return

        if not raw_message:
            return

        # Clear input box immediately
        event.input.value = ""

        # Reset history navigation cursor and save command to persistent history
        self.history_index = -1
        self.history_stash = ""
        if not self.input_history or self.input_history[-1] != raw_message:
            self.input_history.append(raw_message)
            self.save_to_history(raw_message)

        # Display user command bar in conversation log
        self.print_user_prompt_bar(raw_message)

        # Dispatch in background worker thread
        self.dispatch_agent_turn(raw_message)

    @work(exclusive=True, thread=True)
    def dispatch_agent_turn(self, raw_message: str):
        """Run one turn in a worker thread; never leave the UI stuck busy.

        The body below has a try of its own, but only around the agent turn —
        every slash-command branch sits outside it. An exception in any of
        those used to kill the worker with is_running_turn still True, which
        froze the app: no input accepted, ticker never stopped.
        """
        try:
            self._dispatch_agent_turn(raw_message)
        except Exception as error:
            self.safe_call_from_thread(
                self.print_tool_result, f"Turn crashed: {error}", True
            )
        finally:
            self.is_running_turn = False
            self.safe_call_from_thread(self.stop_activity_ticker)
            self.safe_call_from_thread(self.update_status)

    def _dispatch_agent_turn(self, raw_message: str):
        """Execute slash command or agent turn in background worker thread."""
        self.is_running_turn = True
        self._pending_cancel = False
        self.call_from_thread(self.update_status, "⚡ Working... · ctrl+c to interrupt")

        # Unfold any folded paste tags
        unfolded = expand_pasted_blocks(raw_message)
        unfolded = expand_alias(self.cfg, unfolded)
        parts = unfolded.split()
        base_cmd = parts[0].lower() if parts else ""
        cmd_arg = " ".join(parts[1:]) if len(parts) > 1 else ""

        # Slash commands dispatcher
        if base_cmd in ("/exit", "/quit", "exit", "quit"):
            self.call_from_thread(self.exit)
            return

        if base_cmd in ("/clear", "/reset", "/new"):
            self.call_from_thread(self.get_log().clear)
            self.session.reset()
            self.call_from_thread(
                self.print_markdown,
                "history reset and screen cleared.",
            )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd in ("/help", "/"):
            detail = find_command_help(SLASH_COMMANDS, cmd_arg) if cmd_arg.strip() else None
            if detail:
                self.call_from_thread(self.print_markdown, detail)
            else:
                if cmd_arg.strip():
                    self.call_from_thread(
                        self.print_markdown,
                        f"[yellow]Tidak ada command cocok dengan '{cmd_arg}'.[/yellow]",
                    )
                self.call_from_thread(self.print_help_table)
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd in ("/models", "/model") and not cmd_arg:
            self.call_from_thread(
                self.print_models_table, self.cfg.models, self.cfg.active_model
            )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd == "/model" and cmd_arg:
            if self.session.switch_model(cmd_arg):
                self.cfg.active_model = cmd_arg
                self.active_model = cmd_arg
                self.call_from_thread(self.update_banner)
                self.call_from_thread(
                    self.print_slash_result,
                    f"/model {cmd_arg}",
                    f"Set model to {cmd_arg} and saved as your default for new sessions",
                )
            else:
                self.call_from_thread(
                    self.print_markdown,
                    f"[bold red]Model '{cmd_arg}' not found.[/bold red]",
                )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd in ("/steps", "/max_steps", "/limit"):
            if cmd_arg.isdecimal():
                val = max(1, int(cmd_arg))
                self.cfg.max_steps = val
                try:
                    save_config(self.cfg)
                except Exception:
                    pass
                self.call_from_thread(
                    self.print_slash_result,
                    f"/steps {val}",
                    f"Set maximum autonomous tool steps to {val} per turn.",
                )
            else:
                cur = getattr(self.cfg, "max_steps", 50)
                self.call_from_thread(
                    self.print_markdown,
                    f"**Current Max Steps:** `{cur}` steps per turn.\n\n"
                    "Untuk mengubah, gunakan: `/steps 100` (atau `/steps 50`)."
                )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd in ("/save", "/save-session"):
            p = self.session.save()
            self.call_from_thread(
                self.print_slash_result,
                "/save",
                f"Sesi berhasil disimpan ke disk:\n- **Session ID:** `{self.session.session_id}`\n- **File:** `{p}`\n- **Riwayat Pesan:** {len(self.session.messages)}",
            )
            self.is_running_turn = False
            return

        if base_cmd in ("/sessions", "/session-list", "/history"):
            from onno_x.persistence import list_sessions, search_sessions
            query = cmd_arg.strip()
            sessions = search_sessions(query) if query else list_sessions()
            if not sessions:
                self.call_from_thread(
                    self.print_markdown,
                    f"[yellow]Tidak ada sesi yang cocok dengan '{query}'.[/yellow]" if query
                    else "[yellow]Belum ada riwayat sesi yang tersimpan.[/yellow]",
                )
            else:
                table = Table(
                    title=f"📋 Sesi Tersimpan ({len(sessions)})"
                    + (f" · filter: {query}" if query else ""),
                    box=box.ROUNDED,
                )
                table.add_column("#", style="dim", justify="right")
                table.add_column("Session ID", style="bold cyan")
                table.add_column("Judul", style="white", max_width=30)
                table.add_column("Waktu Update", style="dim")
                table.add_column("Model", style="white")
                table.add_column("Pesan", justify="right", style="green")
                table.add_column("Direktori", style="dim")
                for idx, s in enumerate(sessions[:15], start=1):
                    table.add_row(
                        str(idx),
                        s["id"],
                        (s.get("title") or "-")[:30],
                        s["updated_at"][:19].replace("T", " "),
                        s["model_name"],
                        str(s["messages_count"]),
                        s.get("cwd", "")[:35],
                    )
                self.call_from_thread(self.get_log().write, table)
                self.call_from_thread(
                    self.print_markdown,
                    "Ketik `/resume` untuk memuat sesi terakhir, `/resume <nomor>` untuk sesi di daftar, "
                    "atau `/resume <session_id>`. Cari dengan `/sessions <kata>`."
                )
            self.is_running_turn = False
            return

        if base_cmd in ("/resume", "/continue", "/restore"):
            from onno_x.persistence import load_session, get_latest_session, resolve_session_ref
            target_id = cmd_arg.strip() if cmd_arg.strip() not in ("", "latest") else None
            loaded = None
            if not target_id:
                loaded = get_latest_session()
            else:
                resolved = resolve_session_ref(target_id)
                if not resolved and load_session(target_id):
                    # Not in this workspace's listing — accept an exact saved id.
                    resolved = target_id
                if resolved:
                    target_id = resolved
                    loaded = load_session(target_id)
                else:
                    self.call_from_thread(
                        self.print_markdown,
                        f"[bold red]Sesi '{cmd_arg}' tidak ditemukan atau nomornya di luar daftar. "
                        "Cek `/sessions`.[/bold red]",
                    )
                    self.is_running_turn = False
                    return

            if loaded:
                self.session.restore_from_dict(loaded)
                self.active_model = self.session.spec.name
                self.call_from_thread(self.update_banner)
                self.call_from_thread(self.get_log().clear)
                self.call_from_thread(self.render_resumed_session_log)
                self.call_from_thread(
                    self.update_status, f"✔ Sesi {self.session.session_id} berhasil dimuat!"
                )
            else:
                self.call_from_thread(
                    self.print_markdown, f"[bold red]Sesi '{cmd_arg or 'latest'}' tidak ditemukan.[/bold red]"
                )
            self.is_running_turn = False
            return

        if base_cmd in ("/autoresume", "/auto-resume"):
            val = cmd_arg.lower().strip()
            if val in ("on", "true", "1", "yes"):
                self.cfg.auto_resume = True
                try:
                    save_config(self.cfg)
                except Exception:
                    pass
                self.call_from_thread(
                    self.print_slash_result,
                    "/autoresume on",
                    "Auto-resume AKTIF: Onno-X akan otomatis mengingat dan memuat sesi terakhir setiap kali dibuka.",
                )
            elif val in ("off", "false", "0", "no"):
                self.cfg.auto_resume = False
                try:
                    save_config(self.cfg)
                except Exception:
                    pass
                self.call_from_thread(
                    self.print_slash_result,
                    "/autoresume off",
                    "Auto-resume NONAKTIF: Onno-X akan memulai sesi kosong baru setiap kali dibuka.",
                )
            else:
                cur = getattr(self.cfg, "auto_resume", False)
                self.call_from_thread(
                    self.print_markdown,
                    f"**Auto-Resume Status:** `{'AKTIF' if cur else 'NONAKTIF'}`\n\n"
                    "Gunakan `/autoresume on` untuk otomatis mengingat sesi sebelumnya saat dibuka, atau `/autoresume off`.",
                )
            self.is_running_turn = False
            return

        if base_cmd == "/btw":
            if not cmd_arg:
                self.call_from_thread(
                    self.print_markdown,
                    "[yellow]Usage: /btw <pertanyaan sampingan>[/yellow]",
                )
            else:
                # Swallow the renderables/tokens: without callbacks run_turn
                # streams straight into stdout, which paints under the TUI.
                ans = self.session.run_turn(
                    cmd_arg,
                    ephemeral=True,
                    on_output=lambda _renderable: None,
                    on_token=lambda _token: None,
                )
                ans_str = (ans or "").strip().replace("\n", " ")
                if len(ans_str) > 120:
                    ans_str = ans_str[:117] + "..."
                self.call_from_thread(
                    self.update_status, f"💡 btw: {ans_str}"
                )
            self.is_running_turn = False
            return

        # Permission mode commands: /permissions, /mode, /auto, /all, /manual, /yolo
        if base_cmd in ("/permissions", "/mode", "/permission"):
            mode_choice = cmd_arg.lower().strip()
            if mode_choice in ("auto", "manual", "all", "yolo", "accept-all", "accept_all"):
                canon_mode = "all" if mode_choice in ("all", "yolo", "accept-all", "accept_all") else mode_choice
                self.session.permission_mode = canon_mode
                self.call_from_thread(self.update_status)
                self.call_from_thread(
                    self.print_slash_result,
                    f"/mode {canon_mode}",
                    f"Switched permission mode to '{canon_mode.upper()}'. Tools will execute {'directly without asking' if canon_mode in ('auto', 'all') else 'with confirmation for each action'}.",
                )
            else:
                cur_mode = getattr(self.session, "permission_mode", "auto")
                self.call_from_thread(
                    self.print_markdown,
                    f"**Current Permission Mode:** `{cur_mode.upper()}`\n\n"
                    "- `/mode auto` (Default): All safe tools, bash commands, and pentest tools execute **DIRECTLY**.\n"
                    "- `/mode all` (Accept All / YOLO): 100% autonomous execution without any prompts.\n"
                    "- `/mode manual`: Strict verification mode requiring confirmation for every change.\n\n"
                    "*(Tip: You can also press `Shift+Tab` to cycle modes instantly)*"
                )
            self.is_running_turn = False
            return

        if base_cmd in ("/all", "/yolo", "/accept-all"):
            self.session.permission_mode = "all"
            self.call_from_thread(self.update_status)
            self.call_from_thread(
                self.print_slash_result,
                "/mode all",
                "Switched to ACCEPT ALL mode (100% autonomous direct tool execution).",
            )
            self.is_running_turn = False
            return

        if base_cmd == "/auto":
            self.session.permission_mode = "auto"
            self.call_from_thread(self.update_status)
            self.call_from_thread(
                self.print_slash_result,
                "/mode auto",
                "Switched to AUTO mode (Commands and tools execute directly without prompts).",
            )
            self.is_running_turn = False
            return

        if base_cmd == "/manual":
            self.session.permission_mode = "manual"
            self.call_from_thread(self.update_status)
            self.call_from_thread(
                self.print_slash_result,
                "/mode manual",
                "Switched to MANUAL mode (Confirm each tool before execution).",
            )
            self.is_running_turn = False
            return

        if base_cmd in ("/copy", "/cp"):
            target = self.get_latest_response_text()
            if target:
                ok = self.copy_text_to_clipboard(target)
                status_msg = "Copied to clipboard and saved to ~/.onno-x/last_response.txt" if ok else "Saved to ~/.onno-x/last_response.txt"
                self.call_from_thread(
                    self.print_slash_result,
                    "/copy",
                    f"{status_msg} ({len(target)} chars)",
                )
                self.call_from_thread(
                    self.update_status, "✔ Copied last response to clipboard!"
                )
            else:
                self.call_from_thread(
                    self.print_markdown, "[yellow]No response available to copy yet.[/yellow]"
                )
            self.is_running_turn = False
            return

        # --- Utility commands added after the first audit ---
        if base_cmd in ("/test", "/lint"):
            detected = detect_test_command() if base_cmd == "/test" else detect_lint_command()
            target = cmd_arg.strip() or detected
            if not target:
                self.call_from_thread(
                    self.print_markdown,
                    f"[yellow]Tidak mendeteksi {'test runner' if base_cmd == '/test' else 'linter'}. "
                    f"Gunakan {base_cmd} <command>.[/yellow]",
                )
            else:
                self.call_from_thread(self.print_slash_result, base_cmd, f"Menjalankan: {target}")
                code, output = run_shell_capture(target, timeout=900)
                self.call_from_thread(
                    self.get_log().write,
                    Panel(
                        Text(output or "(tidak ada output)"),
                        title=f"{_escape_markup(base_cmd.lstrip('/'))} exit={code}",
                        border_style="green" if code == 0 else "red",
                    ),
                )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd == "/todo":
            action, _, rest = cmd_arg.strip().partition(" ")
            action = action.lower()
            rest = rest.strip()
            if action == "add" and rest:
                n = self.session.add_todo(rest)
                self.call_from_thread(self.print_slash_result, "/todo add", f"#{n} {rest}")
            elif action in ("done", "toggle") and rest.isdecimal():
                text = self.session.complete_todo(int(rest))
                self.call_from_thread(
                    self.print_slash_result, "/todo done", text or f"#{rest} tidak ada"
                )
            elif action in ("rm", "remove", "del") and rest.isdecimal():
                text = self.session.remove_todo(int(rest))
                self.call_from_thread(
                    self.print_slash_result, "/todo rm", text or f"#{rest} tidak ada"
                )
            elif action == "clear":
                self.session.clear_todos()
                self.call_from_thread(self.print_markdown, "[dim]Todo list dikosongkan.[/dim]")
            else:
                if not self.session.todos:
                    self.call_from_thread(
                        self.print_markdown, "[dim]Belum ada todo. /todo add <teks>[/dim]"
                    )
                else:
                    lines = [
                        f"{i}. {'[x]' if t.get('done') else '[ ]'} {t.get('text')}"
                        for i, t in enumerate(self.session.todos, 1)
                    ]
                    self.call_from_thread(
                        self.get_log().write,
                        Panel(Text("\n".join(lines)), title=f"Todo ({len(self.session.todos)})", border_style="cyan"),
                    )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd == "/snapshot":
            name = self.session.save_named_checkpoint(cmd_arg)
            self.call_from_thread(
                self.print_slash_result, "/snapshot", f"'{name}' disimpan ({len(self.session.messages)} pesan)"
            )
            self.is_running_turn = False
            return

        if base_cmd == "/restore":
            if not cmd_arg.strip():
                names = ", ".join(self.session.named_checkpoints) or "(belum ada)"
                self.call_from_thread(self.print_slash_result, "/restore", f"Snapshot: {names}")
            elif self.session.restore_named_checkpoint(cmd_arg):
                self.call_from_thread(
                    self.print_slash_result, "/restore", f"Dipulihkan ke '{cmd_arg.strip()}'"
                )
            else:
                self.call_from_thread(
                    self.print_markdown, f"[red]Snapshot '{cmd_arg.strip()}' tidak ditemukan.[/red]"
                )
            self.call_from_thread(self.update_status)
            self.is_running_turn = False
            return

        if base_cmd == "/undo-file":
            result = self.session.undo_file(cmd_arg.strip()) if cmd_arg.strip() else None
            self.call_from_thread(
                self.print_slash_result,
                "/undo-file",
                result or "Tidak ada snapshot untuk path itu (atau argumen kosong)",
            )
            self.is_running_turn = False
            return

        if base_cmd in ("/grep", "/search"):
            total, text = grep_repo(cmd_arg.strip()) if cmd_arg.strip() else (0, "")
            if not total:
                self.call_from_thread(
                    self.print_markdown, f"[dim]Tidak ada hasil untuk '{cmd_arg.strip()}'.[/dim]"
                )
            else:
                self.call_from_thread(
                    self.get_log().write,
                    Panel(Text(text), title=f"grep: {_escape_markup(cmd_arg.strip())} ({total} baris)", border_style="cyan"),
                )
            self.is_running_turn = False
            return

        if base_cmd == "/find":
            total, text = find_files(cmd_arg.strip()) if cmd_arg.strip() else (0, "")
            self.call_from_thread(
                self.get_log().write,
                Panel(Text(text or "(tidak ada hasil)"), title=f"find: {_escape_markup(cmd_arg.strip())} ({total} file)", border_style="cyan"),
            )
            self.is_running_turn = False
            return

        if base_cmd == "/stash":
            parts_ = cmd_arg.split(maxsplit=1)
            action_ = parts_[0].lower() if parts_ else "list"
            label_ = parts_[1] if len(parts_) > 1 else ""
            ok, text = git_stash(action_, label_)
            self.call_from_thread(
                self.get_log().write,
                Panel(Text(text), title=f"git stash {_escape_markup(action_)}", border_style="green" if ok else "red"),
            )
            self.is_running_turn = False
            return

        if base_cmd == "/autoverify":
            choice = cmd_arg.lower().strip()
            if choice in ("on", "enable", "true", "1"):
                self.cfg.auto_verify = True
            elif choice in ("off", "disable", "false", "0"):
                self.cfg.auto_verify = False
            elif choice:
                self.call_from_thread(
                    self.print_markdown, "[yellow]Usage: /autoverify [on|off][/yellow]"
                )
                self.is_running_turn = False
                return
            else:
                self.cfg.auto_verify = not getattr(self.cfg, "auto_verify", True)
            try:
                save_config(self.cfg)
            except Exception:
                pass
            state = "AKTIF" if self.cfg.auto_verify else "NONAKTIF"
            self.call_from_thread(
                self.print_slash_result,
                f"/autoverify {state.lower()}",
                f"Auto-verify {state}: test/lint project dijalankan setelah turn yang mengubah file.",
            )
            self.is_running_turn = False
            return

        if base_cmd == "/draft":
            from onno_x.persistence import clear_draft, load_draft

            if cmd_arg.lower().strip() in ("clear", "hapus", "delete", "-d"):
                removed = clear_draft()
                self.call_from_thread(
                    self.print_slash_result,
                    "/draft clear",
                    "Draft dihapus." if removed else "Tidak ada draft tersimpan.",
                )
            else:
                draft = load_draft()
                if not draft:
                    self.call_from_thread(
                        self.print_markdown, "[dim]Tidak ada draft untuk direktori ini.[/dim]"
                    )
                else:
                    self.call_from_thread(
                        self.get_log().write,
                        Panel(
                            Text(draft["text"]),
                            title=f"Draft tersimpan {_escape_markup(str(draft.get('saved_at', '')))}",
                            border_style="cyan",
                        ),
                    )
            self.is_running_turn = False
            return

        if base_cmd == "/log":
            n = int(cmd_arg) if cmd_arg.strip().isdecimal() else 10
            ok, text = git_log(n)
            self.call_from_thread(
                self.get_log().write,
                Panel(Text(text), title=f"git log -{n}", border_style="yellow" if ok else "red"),
            )
            self.is_running_turn = False
            return

        if base_cmd == "/tokens":
            rows = token_breakdown(self.session.messages)
            total_tok = sum(r[2] for r in rows) or 1
            table = Table(title="Token Breakdown (approx)", box=box.ROUNDED)
            table.add_column("Kategori", style="bold cyan")
            table.add_column("Pesan", justify="right")
            table.add_column("Token", justify="right")
            table.add_column("Porsi", justify="right")
            for cat_, count_, tok_ in rows:
                table.add_row(cat_, str(count_), f"~{tok_:,}", f"{tok_ * 100 / total_tok:.0f}%")
            self.call_from_thread(self.get_log().write, table)
            self.call_from_thread(
                self.print_markdown, f"**Total:** ~{total_tok:,} token"
            )
            self.is_running_turn = False
            return

        if base_cmd == "/alias":
            body = cmd_arg.strip()
            if not body:
                text = "\n".join(f"/{k} → {v}" for k, v in sorted(self.cfg.aliases.items())) or "(belum ada alias)"
                self.call_from_thread(self.print_slash_result, "/alias", text)
            elif body.split(maxsplit=1)[0].lower() in ("rm", "remove", "del"):
                name_ = body.split(maxsplit=1)[1].strip() if len(body.split(maxsplit=1)) > 1 else ""
                if self.cfg.aliases.pop(name_, None) is not None:
                    save_config(self.cfg)
                    self.call_from_thread(self.print_slash_result, "/alias", f"'{name_}' dihapus")
                else:
                    self.call_from_thread(self.print_markdown, f"[yellow]Alias '{name_}' tidak ada.[/yellow]")
            else:
                name_, _, target_ = body.partition(" ")
                name_ = name_.lstrip("/").strip()
                target_ = target_.strip()
                if name_ and target_.startswith("/"):
                    self.cfg.aliases[name_] = target_
                    save_config(self.cfg)
                    self.call_from_thread(self.print_slash_result, "/alias", f"/{name_} → {target_}")
                else:
                    self.call_from_thread(
                        self.print_markdown, "[yellow]Usage: /alias <nama> </command ...>[/yellow]"
                    )
            self.is_running_turn = False
            return

        if base_cmd in ("/title", "/session"):
            body = cmd_arg.strip()
            if base_cmd == "/session" and body.lower().startswith("title"):
                body = body[5:].strip()
            if body:
                self.session.title = body[:120]
                try:
                    self.session.save()
                except Exception:
                    pass
                self.call_from_thread(self.print_slash_result, "/title", self.session.title)
            else:
                self.call_from_thread(
                    self.print_slash_result, "/title", self.session.title or "(belum diset)"
                )
            self.is_running_turn = False
            return

        # Standard agent prompt execution
        try:
            prompt_with_files = expand_at_file_mentions(unfolded)
            self.call_from_thread(
                self.start_activity_ticker,
                f"🧠 Membaca konteks & berpikir ({self.active_model})...",
            )

            current_stream_widget = [None]
            accumulated_text = [""]
            last_render_time = [0.0]

            def ui_output(renderable):
                # When a tool call or output arrives, seal previous streaming widget
                current_stream_widget[0] = None
                accumulated_text[0] = ""
                self.activity_kind = "reading"
                self.call_from_thread(self.get_log().write, renderable)

            tokens_received = [0]
            start_time = time.time()

            def ui_on_token(token: str):
                tokens_received[0] += 1
                accumulated_text[0] += token
                now = time.time()
                buf = accumulated_text[0]

                # Remove every reasoning block, not just the first tag the
                # provider happens to use. Providers vary (think/thinking/
                # reasoning) and some emit more than one block per reply.
                visible_text = strip_reasoning(buf).lstrip("\n")
                if visible_text.startswith("<") and len(visible_text) < 9 and ">" not in visible_text:
                    # Partial opening tag such as '<thi' while the stream is mid-tag.
                    visible_text = ""
                in_think = not visible_text

                # Update activity ticker: distinguish thinking vs writing response
                elapsed = now - start_time
                spd = tokens_received[0] / max(0.1, elapsed)
                if in_think:
                    self.activity_kind = "thinking"
                    self.activity_detail = f"🧠 Berpikir ({tokens_received[0]} tokens, {spd:.1f} t/s)"
                else:
                    self.activity_kind = "generating"
                    self.activity_detail = f"⚡ Menulis respons ({tokens_received[0]} tokens, {spd:.1f} t/s)"

                # Only render visible response to conversation log (hide reasoning tokens)
                if visible_text:
                    if current_stream_widget[0] is None:
                        w = SelectableAnswer("")
                        self.call_from_thread(self.get_log().write, w)
                        current_stream_widget[0] = w

                    if (now - last_render_time[0] > 0.035) or ("\n" in token):
                        last_render_time[0] = now
                        w = current_stream_widget[0]
                        self.call_from_thread(w.set_answer, visible_text)
                        self.call_from_thread(self.get_log().scroll_end, animate=False)

            def ui_on_status(kind: str, detail: str):
                self.activity_kind = kind
                self.activity_detail = detail

            if self.on_submit:
                res = self.on_submit(prompt_with_files, self)
                if inspect.isawaitable(res):
                    import asyncio

                    res = asyncio.run(res)
                if isinstance(res, str) and res.strip():
                    self.last_response = res
                    self.copy_text_to_clipboard(res)
                    self.call_from_thread(self.print_markdown, res)
            else:
                # Execute full agent turn streaming directly into conversation log
                turn_res = self.session.run_turn(
                    prompt_with_files,
                    on_output=ui_output,
                    on_token=ui_on_token,
                    on_status=ui_on_status,
                )
                # Final flush of streamed markdown (reasoning blocks removed).
                final_visible = strip_reasoning(accumulated_text[0]).lstrip("\n")

                if current_stream_widget[0] is not None and final_visible:
                    self.call_from_thread(current_stream_widget[0].set_answer, final_visible)
                    self.call_from_thread(self.get_log().scroll_end, animate=False)

                if turn_res:
                    clean_res = strip_reasoning(turn_res).strip()
                    self.last_response = clean_res
                    self.copy_text_to_clipboard(clean_res)

        except InterruptedError:
            try:
                # Keep the prompt so it can be sent again after an accidental ESC.
                from onno_x.persistence import save_draft

                save_draft(prompt_with_files)
            except Exception:
                pass
            self.call_from_thread(
                self.print_markdown,
                "[bold yellow]⚡ Turn was cancelled by user (ESC).[/bold yellow]\n"
                "[dim]Draft disimpan — muat lagi dengan /draft, kirim ulang, atau buang dengan /draft clear.[/dim]",
            )
        except Exception as error:
            self.call_from_thread(self.print_tool_result, str(error), error=True)

        finally:
            self.is_running_turn = False
            self.call_from_thread(self.stop_activity_ticker)
            self.call_from_thread(self.update_status)


# ==========================================
# ENTRY POINT
# ==========================================


def run_tui(active_model: Optional[str] = None):
    from onno_x.interrupt import install_interrupt_guard

    install_interrupt_guard()
    cfg = load_config()
    model = active_model or cfg.active_model
    app = OnnoXUI(active_model=model)
    # Keep mouse reporting for scroll and TextArea drag selection.
    app.run(mouse=True)


if __name__ == "__main__":
    run_tui()