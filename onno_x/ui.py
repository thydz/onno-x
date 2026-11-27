import difflib
from pathlib import Path
import shutil
import sys
from typing import Optional, List, Tuple
from rich import box
from rich.console import Console
from rich.errors import MarkupError, MissingStyle
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.markup import escape as _escape_markup
from rich.table import Table


console = Console()


def _install_tolerant_markup() -> None:
    """Make Rich render unparseable markup literally instead of raising.

    Untrusted text — file paths, grep hits, model output, todo items — often
    contains a '[...]' Rich reads as a closing tag with no opener. The
    MarkupError escapes through Panel/Table titles into Textual's layout pass
    and kills the app mid-turn. Each entry point Rich parses markup through is
    patched once here, at import time, so no call site has to remember.
    """
    import rich.console as _console_mod
    import rich.markup as _markup_mod
    import rich.text as _text_mod

    original = _markup_mod.render

    def tolerant(text, *args, **kwargs):
        try:
            return original(text, *args, **kwargs)
        except (MarkupError, MissingStyle):
            base = kwargs.get("style")
            if base is None and args:
                base = args[0]
            return Text(str(text), style=base or "")

    tolerant.RE_TAGS = getattr(original, "RE_TAGS", None)
    _markup_mod.render = tolerant
    _console_mod.render_markup = tolerant
    _text_mod.render = tolerant

    _orig_from_markup = _text_mod.Text.from_markup

    def from_markup(cls, text, *args, **kwargs):
        try:
            return _orig_from_markup.__func__(cls, text, *args, **kwargs)
        except (MarkupError, MissingStyle):
            return Text(str(text), style=kwargs.get("style") or "")

    _text_mod.Text.from_markup = classmethod(from_markup)


_install_tolerant_markup()


ASCII_ART = r"""
                                    M""MMMM""M                         dP
                                    M  `MM'  M                         88
.d8888b. 88d888b. 88d888b. .d8888b. MM.    .MM .d8888b. .d8888b. .d888b88 .d8888b.
88'  `88 88'  `88 88'  `88 88'  `88 M  .mm.  M 88'  `"" 88'  `88 88'  `88 88ooood8
88.  .88 88    88 88    88 88.  .88 M  MMMM  M 88.  ... 88.  .88 88.  .88 88.  ...
`88888P' dP    dP dP    dP `88888P' M  MMMM  M `88888P' `88888P' `88888P8 `88888P'
                                    MMMMMMMMMM"""


ACCENT_COLORS = ["cyan", "magenta", "green", "yellow", "blue", "red", "white", "default"]


def resolve_accent(name: Optional[str]) -> str:
    """Map a config value to a Rich colour; 'default' and junk fall back to cyan.

    Nilai sembarang dari config (mis. "chartreuse") akan membuat Rich melempar
    MissingStyle saat panel dirender, jadi validitas warna dicek di sini.
    """
    from rich.color import Color

    value = (name or "").strip().lower()
    if value in ("", "default"):
        return "cyan"
    try:
        Color.parse(value)
    except Exception:
        return "cyan"
    return value


# Pasangan warna gradient per accent: (awal, akhir).
GRADIENTS = {
    "cyan": ("#22d3ee", "#818cf8"),
    "magenta": ("#f472b6", "#fb923c"),
    "green": ("#4ade80", "#22d3ee"),
    "yellow": ("#facc15", "#fb7185"),
    "blue": ("#60a5fa", "#c084fc"),
    "red": ("#f87171", "#facc15"),
    "white": ("#e5e7eb", "#94a3b8"),
}


def _rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def gradient_text(content: str, start: str, end: str, bold: bool = True) -> Text:
    """Warnai teks per karakter dengan interpolasi horizontal start→end."""
    r1, g1, b1 = _rgb(start)
    r2, g2, b2 = _rgb(end)
    out = Text()
    lines = content.split("\n")
    span = max(1, max((len(line) for line in lines), default=1) - 1)
    for row, line in enumerate(lines):
        for col, ch in enumerate(line):
            if ch == " ":
                out.append(" ")
                continue
            t = col / span
            color = "#%02x%02x%02x" % (
                round(r1 + (r2 - r1) * t),
                round(g1 + (g2 - g1) * t),
                round(b1 + (b2 - b1) * t),
            )
            out.append(ch, style=f"bold {color}" if bold else color)
        if row < len(lines) - 1:
            out.append("\n")
    return out


def print_banner(
    active_model: str,
    accent: Optional[str] = None,
    cwd: Optional[str] = None,
    session_id: Optional[str] = None,
) -> int:
    """Cetak banner pembuka. Mengembalikan jumlah baris yang dipakai."""
    color = resolve_accent(accent)
    start, end = GRADIENTS.get(color, GRADIENTS["cyan"])
    from onno_x import __version__

    if cwd is None:
        cwd = str(Path.cwd())
    home = str(Path.home())
    if cwd == home:
        display_cwd = "~"
    elif cwd.startswith(home + "/"):
        display_cwd = "~" + cwd[len(home):]
    else:
        display_cwd = cwd

    body = Text()
    if console.width >= 86:
        # Rapikan indentasi seni ASCII lalu pusatkan di dalam panel, supaya
        # wordmark tidak menempel ke kiri pada terminal lebar.
        import textwrap

        art_lines = [line.rstrip() for line in textwrap.dedent(ASCII_ART).strip("\n").splitlines()]
        art_width = max((len(line) for line in art_lines), default=0)
        usable = max(art_width, console.width - 8)
        pad = max(0, (usable - art_width) // 2)
        centered = "\n".join(" " * pad + line for line in art_lines)
        body.append_text(gradient_text(centered, start, end))
        body.append("\n\n")
    else:
        body.append_text(gradient_text("ONNO-X", start, end, bold=True))
        body.append("\n")

    # Tagline + versi
    body.append("multi-model coding agent", style="italic #cbd5e1")
    body.append(f"  ·  v{__version__}", style="dim")
    body.append("\n")

    # Baris status: model aktif, folder kerja, sesi
    body.append("◆ ", style=f"bold {start}")
    body.append(active_model, style="bold white")
    if display_cwd:
        body.append("   ◆ ", style=f"bold {end}")
        body.append(display_cwd, style="dim white")
    if session_id and session_id != "default":
        short = session_id if len(session_id) <= 16 else session_id[:14] + "…"
        body.append("   ◆ ", style=f"bold {end}")
        body.append(short, style="dim")
    body.append("\n")

    hint = Text()
    hint.append("/help", style=f"bold {color}")
    hint.append(" commands  ·  ", style="dim")
    hint.append("@", style=f"bold {color}")
    hint.append(" mention files  ·  ", style="dim")
    hint.append("Ctrl+C", style=f"bold {color}")
    hint.append(" exit", style="dim")
    body.append_text(hint)

    console.print(
        Panel(
            body,
            box=box.ROUNDED,
            border_style=color,
            padding=(0, 2),
            subtitle="  onno-x  ",
            subtitle_align="right",
        )
    )
    return len(body.plain.split("\n")) + 2


def pad_to_bottom(banner_lines: int = 6, input_box_lines: int = 4) -> None:
    """Pad blank lines so that the input box sits directly on the bottom floor without empty gaps."""
    terminal_lines = shutil.get_terminal_size((80, 24)).lines
    needed_padding = max(0, terminal_lines - (banner_lines + input_box_lines))
    if needed_padding > 0:
        print("\n" * needed_padding, end="", flush=True)


def create_rounded_prompt_message(session=None) -> List[Tuple[str, str]]:
    """Render rounded top border: ╭────────────────────────────────────────────╮ spanning full width."""
    cols = shutil.get_terminal_size((80, 20)).columns
    box_width = max(20, cols - 1)
    top_line = "╭" + "─" * (box_width - 2) + "╮"

    tokens = [
        ("class:prompt.divider", f"{top_line}\n"),
        ("class:prompt.edge", "│ "),
    ]
    if session and getattr(session, "plan_mode", False):
        tokens.append(("class:prompt.plan", "[PLAN] "))
    tokens.append(("class:prompt.arrow", "❯ "))
    return tokens


def create_rounded_bottom_toolbar(session=None, btw_state: Optional[dict] = None) -> List[Tuple[str, str]]:
    """Render rounded bottom border: ╰────────────────────────────────────────────╯ and status bar."""
    cols = shutil.get_terminal_size((80, 20)).columns
    box_width = max(20, cols - 1)
    bottom_line = "╰" + "─" * (box_width - 2) + "╯"

    tokens = [
        ("class:toolbar.border", f"{bottom_line}\n"),
    ]
    if btw_state and btw_state.get("active"):
        tokens.append(("class:toolbar.btw.label", " 💡 btw: "))
        ans_preview = btw_state.get("answer", "")
        if len(ans_preview) > 180:
            ans_preview = ans_preview[:175] + "..."
        tokens.append(("class:toolbar.btw.text", f"{ans_preview}\n"))
        tokens.append(("class:toolbar.dim", " (ephemeral answer shown under input box) \n"))

    mode = "auto"
    plan_badge = ""
    if session:
        mode = getattr(session, "permission_mode", "auto").lower()
        plan_badge = " [PLAN]" if getattr(session, "plan_mode", False) else ""

    tokens.extend([
        ("class:toolbar.arrow", "▶▶ "),
        ("class:toolbar.mode", f"{mode} mode on{plan_badge} "),
        ("class:toolbar.dim", "(shift+tab to cycle) · esc to interrupt"),
    ])
    return tokens


def get_rounded_rprompt() -> List[Tuple[str, str]]:
    """Right-side closing wall │ to close the rounded box seamlessly."""
    return [("class:prompt.edge", "│")]


def rounded_prompt_continuation(width: int, line_number: int, is_soft_wrap: bool = False) -> List[Tuple[str, str]]:
    """Keep rounded box vertical edge enclosed on multiline input."""
    return [("class:prompt.edge", "│   ")]

def print_user_prompt_bar(text: str) -> None:
    """Render full-width highlighted user command bar matching Claude Code CLI."""
    import shutil
    cols = shutil.get_terminal_size((80, 20)).columns
    clean_text = text.replace("\n", " ").strip()
    if len(clean_text) > 200:
        clean_text = clean_text[:197] + "..."
    rendered = f" ❯ {clean_text} "
    content = f" ❯ {_escape_markup(clean_text)} "
    fill = " " * max(0, cols - len(rendered) - 1)
    console.print(f"[bold white on #282838]{content}{fill}[/bold white on #282838]")


def print_markdown(content: str) -> None:
    console.print(Markdown(content))


def print_tool_call(name: str, args: dict) -> None:
    safe_name = _escape_markup(str(name))
    safe_args = _escape_markup(str(args))
    console.print(f"[bold yellow]⚙ Executing tool:[/bold yellow] [green]{safe_name}[/green] {safe_args}")


def print_tool_result(result: str, error: bool = False) -> None:
    color = "red" if error else "dim white"
    snippet = result.strip()
    if len(snippet) > 800:
        snippet = snippet[:800] + "\n... (truncated)"
    console.print(Panel(Text(snippet), border_style=color, title="Tool Output", title_align="left"))


def print_file_diff(file_path: str, old_text: str, new_text: str) -> None:
    """Print colored unified diff of file modification."""
    diff_lines = list(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=3,
    ))
    if not diff_lines:
        return

    diff_str = "".join(diff_lines)
    syntax = Syntax(diff_str, "diff", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"File Modification Diff: {_escape_markup(str(file_path))}", border_style="yellow"))


def print_models_table(models: dict, active: str) -> None:
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
    console.print(table)
