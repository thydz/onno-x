import difflib
from pathlib import Path
import shutil
import sys
from typing import Optional, List, Tuple
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.table import Table

console = Console()


ASCII_ART = r"""
                                    M""MMMM""M                         dP
                                    M  `MM'  M                         88
.d8888b. 88d888b. 88d888b. .d8888b. MM.    .MM .d8888b. .d8888b. .d888b88 .d8888b.
88'  `88 88'  `88 88'  `88 88'  `88 M  .mm.  M 88'  `"" 88'  `88 88'  `88 88ooood8
88.  .88 88    88 88    88 88.  .88 M  MMMM  M 88.  ... 88.  .88 88.  .88 88.  ...
`88888P' dP    dP dP    dP `88888P' M  MMMM  M `88888P' `88888P' `88888P8 `88888P'
                                    MMMMMMMMMM"""


def print_banner(active_model: str) -> None:
    text = Text()
    if console.width >= 86:
        text.append(ASCII_ART + "\n\n", style="bold cyan")
    else:
        text.append("ONNO-X", style="bold cyan")
        text.append(" | Coding Agent CLI\n", style="bold white")
    text.append(f"Model: {active_model}  •  Type /help for commands, Ctrl+C to exit", style="dim white")
    console.print(Panel(text, border_style="cyan", padding=(0, 1)))


def pad_to_bottom(banner_lines: int = 6, input_box_lines: int = 4) -> None:
    """Pad blank lines so that the input box sits directly on the bottom floor without empty gaps."""
    terminal_lines = shutil.get_terminal_size((80, 24)).lines
    # Total lines: banner (6) + input box & toolbar (4) = 10 lines
    needed_padding = max(0, terminal_lines - 10)
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
    content = f" ❯ {clean_text} "
    fill = " " * max(0, cols - len(content) - 1)
    console.print(f"[bold white on #282838]{content}{fill}[/bold white on #282838]")


def print_markdown(content: str) -> None:
    console.print(Markdown(content))


def print_tool_call(name: str, args: dict) -> None:
    console.print(f"[bold yellow]⚙ Executing tool:[/bold yellow] [green]{name}[/green] {args}")


def print_tool_result(result: str, error: bool = False) -> None:
    color = "red" if error else "dim white"
    snippet = result.strip()
    if len(snippet) > 800:
        snippet = snippet[:800] + "\n... (truncated)"
    console.print(Panel(snippet, border_style=color, title="Tool Output", title_align="left"))


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
    console.print(Panel(syntax, title=f"File Modification Diff: {file_path}", border_style="yellow"))


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
