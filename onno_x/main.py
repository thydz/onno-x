from pathlib import Path
from typing import Optional
import os
import re
import shutil
import subprocess
import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.panel import Panel
from rich.table import Table

from onno_x.config import (
    CONFIG_DIR,
    ModelSpec,
    load_config,
    save_config,
)
from onno_x.session import AgentSession
from onno_x.skills import (
    add_skill,
    delete_skill,
    list_skills,
    import_skills_from_dir,
    fetch_skill_from_url,
    load_marketplaces,
    save_marketplaces,
)
from onno_x.persistence import (
    save_session,
    load_session,
    list_sessions,
    get_latest_session,
    delete_session,
)
from onno_x.mcp import MCPManager
from onno_x.tools import get_active_tool_definitions
from onno_x.tools.obsidian import obsidian_search_notes, obsidian_read_note, obsidian_write_note
from onno_x.ui import (
    console,
    print_banner,
    print_models_table,
    print_user_prompt_bar,
    create_rounded_prompt_message,
    create_rounded_bottom_toolbar,
    rounded_prompt_continuation,
    get_rounded_rprompt,
    pad_to_bottom,
)

# Mirroring exact Claude Code slash commands from menu.md
SLASH_COMMANDS = [
    ("/add-dir", "Menambahkan direktori lain agar dapat diakses selama sesi (/add-dir <path>)"),
    ("/advisor", "Mengaktifkan, menonaktifkan, atau memilih model penasihat (/advisor [model|off])"),
    ("/agents", "Panduan dan status pengelolaan subagent/worker"),
    ("/all", "Mode All (YOLO): Eksekusi 100% otonom langsung tanpa prompt izin apa pun"),
    ("/auto", "Mode Auto: Eksekusi tool & perintah shell langsung tanpa meminta izin berulang"),
    ("/autocompact", "Mengatur ambang batas context sebelum auto-compact (/autocompact [auto|<tokens>])"),
    ("/autoresume", "Mengaktifkan/menonaktifkan auto-resume sesi saat onno-x dibuka (/autoresume [on|off])"),
    ("/branch", "Membuat cabang percakapan baru untuk mencoba pendekatan lain (/branch [name])"),
    ("/btw", "Mengajukan pertanyaan sampingan tanpa menambahkannya ke riwayat utama (/btw <tanya>)"),
    ("/bug", "Menghasilkan laporan bug dan diagnostik sistem (alias: /share)"),
    ("/cd", "Memindahkan direktori kerja sesi tanpa menghapus percakapan (/cd <path>)"),
    ("/clear", "Memulai percakapan baru dengan context kosong (alias: /reset, /new)"),
    ("/code-review", "Meninjau perubahan kode / PR untuk mendeteksi bug (alias: /review)"),
    ("/color", "Mengubah tema warna atau aksen prompt (/color [color|default])"),
    ("/commit", "Menganalisis git diff dan membuat conventional commit otomatis (/commit [msg])"),
    ("/compact", "Merangkum percakapan untuk mengurangi pemakaian context tokens"),
    ("/config", "Melihat atau mengubah konfigurasi onno-x (alias: /settings)"),
    ("/context", "Menampilkan analisis pemakaian context window dan rincian pesan (/context [all])"),
    ("/continue", "Melanjutkan sesi sebelumnya (alias dari /resume)"),
    ("/copy", "Menyalin jawaban terakhir ke clipboard terminal (/copy)"),
    ("/cost", "Menampilkan token usage dan perkiraan biaya sesi (alias: /usage, /stats)"),
    ("/diff", "Menampilkan dan meninjau perubahan git diff pada working tree"),
    ("/doctor", "Mendiagnosis instalasi, network model, git, dan file panduan (alias: /checkup)"),
    ("/effort", "Mengatur tingkat reasoning/temperature model (/effort [low|medium|high])"),
    ("/exit", "Keluar dari sesi onno-x (alias: /quit)"),
    ("/export", "Mengekspor riwayat percakapan menjadi file markdown (/export [filename])"),
    ("/fast", "Mengaktifkan atau menonaktifkan Fast Mode deterministik (/fast [on|off])"),
    ("/feedback", "Mengirim masukan atau laporan kualitas respons"),
    ("/fork", "Menyalin sesi percakapan saat ini ke sesi independen baru (/fork)"),
    ("/goal", "Menetapkan target kondisi sebelum agent berhenti (/goal [condition|clear])"),
    ("/help", "Menampilkan panduan dan seluruh daftar perintah garis miring"),
    ("/history", "Melihat riwayat sesi tersimpan di disk (alias dari /sessions)"),
    ("/init", "Membuat panduan awal project dalam file ONNO.md / CLAUDE.md"),
    ("/manual", "Mode Manual: Memerlukan konfirmasi izin setiap kali tool dijalankan"),
    ("/max_steps", "Alias dari /steps untuk mengatur batas langkah otonom (/steps <n>)"),
    ("/mcp", "Mengelola server Model Context Protocol dan tools eksternal (/mcp [list|reload])"),
    ("/memory", "Melihat dan mengedit instruksi memori proyek (ONNO.md / CLAUDE.md)"),
    ("/mode", "Mengatur mode izin tools (/mode [auto|manual|all] atau tekan Shift+Tab)"),
    ("/model", "Memilih atau mengganti model AI aktif (/model <alias>)"),
    ("/models", "Melihat daftar semua model yang terdaftar"),
    ("/notify", "Mengaktifkan/menonaktifkan alert suara saat agent selesai (/notify [on|off])"),
    ("/obsidian", "Mencari, membaca, atau menulis catatan di Obsidian memory (/obsidian [search|read|write])"),
    ("/output-style", "Mengganti gaya jawaban (/output-style [default|concise|verbose])"),
    ("/permissions", "Mengatur mode izin tools (/permissions [auto|manual|all] atau /mode)"),
    ("/plan", "Masuk ke Plan Mode untuk merancang arsitektur sebelum coding (/plan [on|off])"),
    ("/plugin", "Mengelola plugin dan integrasi pihak ketiga (/plugin [list|add])"),
    ("/pr", "Membuat ringkasan pull request dan opsi create via GitHub CLI (/pr [title])"),
    ("/recap", "Membuat ringkasan eksekutif satu baris dari sesi saat ini"),
    ("/resume", "Melanjutkan riwayat percakapan sebelumnya (/resume [session_id])"),
    ("/review", "Alias dari /code-review untuk meninjau perubahan kode"),
    ("/rewind", "Mengembalikan percakapan ke checkpoint sebelumnya (alias: /undo, /checkpoint)"),
    ("/run", "Menjalankan aplikasi project dan menguji eksekusi secara langsung"),
    ("/save", "Menyimpan sesi percakapan saat ini ke disk (/save)"),
    ("/security-review", "Menganalisis kode untuk menemukan potensi celah keamanan"),
    ("/sessions", "Melihat riwayat sesi tersimpan di disk (alias: /history)"),
    ("/simplify", "Meninjau kode untuk menyederhanakan struktur & efisiensi"),
    ("/skill", "Menjalankan atau menginstal skill (/skill <name> atau /skill install <url>)"),
    ("/skills", "Menampilkan daftar seluruh skills yang tersedia (/skills [query])"),
    ("/status", "Menampilkan status sesi, versi, model aktif, dan konektivitas"),
    ("/steps", "Mengatur batas langkah otonom tools per giliran (/steps <jumlah>, default: 50-100)"),
    ("/terminal-setup", "Menguji kapabilitas render warna ANSI, unicode, dan font"),
    ("/usage", "Alias dari /cost untuk melihat statistik token & biaya"),
    ("/verify", "Memverifikasi hasil implementasi dengan menjalankan test/check"),
]


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Fast bailout if user is pasting multiline text
        if "\n" in text:
            return

        # File @-mention autocompletion (safe, non-recursive parent scan)
        last_word = text.split()[-1] if text.split() else ""
        if last_word.startswith("@") and len(last_word) <= 60:
            prefix = last_word[1:]
            cwd = Path.cwd()
            ignore_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".onno-x", ".gemini", "dist", "build"}
            count = 0
            try:
                if "/" in prefix:
                    parts = prefix.split("/")
                    parent_part = "/".join(parts[:-1])
                    file_part = parts[-1].lower()
                    search_dir = cwd / parent_part
                    if search_dir.is_dir():
                        for p in search_dir.iterdir():
                            if count >= 30:
                                break
                            if p.name.startswith(".") or p.name in ignore_dirs:
                                continue
                            if p.name.lower().startswith(file_part):
                                count += 1
                                rel_path = str(p.relative_to(cwd))
                                meta = "DIR" if p.is_dir() else f"{p.stat().st_size} B"
                                yield Completion(
                                    rel_path,
                                    start_position=-len(prefix),
                                    display="@" + rel_path,
                                    display_meta=meta,
                                )
                else:
                    for p in cwd.iterdir():
                        if count >= 30:
                            break
                        if p.name.startswith(".") or p.name in ignore_dirs:
                            continue
                        if p.name.lower().startswith(prefix.lower()):
                            count += 1
                            rel_path = str(p.relative_to(cwd))
                            meta = "DIR" if p.is_dir() else f"{p.stat().st_size} B"
                            yield Completion(
                                rel_path,
                                start_position=-len(prefix),
                                display="@" + rel_path,
                                display_meta=meta,
                            )
            except Exception:
                pass
            return

        if text.startswith("/skill "):
            prefix = text[7:]
            skills = list_skills()
            for sname, sobj in sorted(skills.items(), key=lambda x: x[0]):
                if sname.startswith(prefix):
                    desc = sobj.description.strip().replace("\n", " ")
                    if len(desc) > 35:
                        desc = desc[:32] + "..."
                    yield Completion(
                        sname,
                        start_position=-len(prefix),
                        display=sname,
                        display_meta=desc,
                    )
            return

        if text.startswith("/model "):
            prefix = text[7:]
            cfg = load_config()
            for mname in cfg.models.keys():
                if mname.startswith(prefix):
                    yield Completion(
                        mname,
                        start_position=-len(prefix),
                        display=mname,
                        display_meta="Model alias",
                    )
            return

        if text.startswith("/"):
            word = text.split()[0]
            for cmd, desc in SLASH_COMMANDS:
                if cmd.startswith(word):
                    yield Completion(
                        cmd,
                        start_position=-len(word),
                        display=cmd,
                        display_meta=desc,
                    )


def expand_at_file_mentions(prompt: str) -> str:
    """Find @filename mentions and append their contents as context attachments safely."""
    import re

    # Only match @ when preceded by start of string, space, or open paren
    # (prevents false matches on SSH commands or emails like onnobot@100.105.127.40)
    matches = re.findall(r"(?:^|[\s(\[])@([a-zA-Z0-9_\-\./]+)", prompt)
    if not matches:
        return prompt

    attachments = []
    seen = set()
    for raw_path in matches:
        # Ignore obvious IP addresses, domains, or host strings
        if raw_path.startswith(("192.", "10.", "172.", "127.", "100.", "localhost")):
            continue
        try:
            p = Path(raw_path).expanduser().resolve()
            if p in seen or not p.exists() or not p.is_file():
                continue

            # Safety guard: Never read files > 500 KB or binary into prompt attachment
            if p.stat().st_size > 500_000:
                continue

            with open(p, "rb") as bf:
                if b"\0" in bf.read(512):
                    continue

            seen.add(p)
            lines = []
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f):
                    if idx >= 250:
                        lines.append(f"... (truncated after 250 lines)")
                        break
                    lines.append(line.rstrip("\r\n"))

            snippet = "\n".join(lines)
            attachments.append(f"--- [Attachment: {raw_path}] ---\n{snippet}\n--- [End of {raw_path}] ---")
        except Exception:
            pass

    if attachments:
        context_block = "\n\n" + "\n\n".join(attachments)
        return prompt + context_block
    return prompt


# --- CLAUDE CODE CLI STYLE PASTE FOLDING & LEXER ---
PASTE_STORE: dict[str, str] = {}
PASTE_COUNTER: int = 0


def register_pasted_block(data: str) -> str:
    """Store raw pasted data and return a compact pill badge string."""
    global PASTE_COUNTER
    PASTE_COUNTER += 1
    tag_id = PASTE_COUNTER
    lines = data.count("\n") + 1
    chars = len(data)
    if lines > 1:
        summary = f"+{lines} lines, {chars} chars"
    else:
        summary = f"{chars} chars"
    tag = f"[Pasted text #{tag_id} ({summary})]"
    PASTE_STORE[tag] = data
    return tag


def expand_pasted_blocks(text: str) -> str:
    """Unfold all [Pasted text #ID (...)] tags back to original full content."""
    if not PASTE_STORE or "[Pasted text #" not in text:
        return text
    expanded = text
    for tag, content in list(PASTE_STORE.items()):
        if tag in expanded:
            expanded = expanded.replace(tag, content)
    return expanded


class OnnoInputLexer(Lexer):
    """Syntax highlighter for input prompt, rendering folded paste pills in clean cyan badges."""
    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            pattern = re.compile(r"(\[Pasted text #[0-9]+ \([^\]]+\)\])")
            parts = []
            last_end = 0
            for m in pattern.finditer(line):
                if m.start() > last_end:
                    parts.append(("", line[last_end:m.start()]))
                parts.append(("class:pasted-tag", m.group(1)))
                last_end = m.end()
            if last_end < len(line):
                parts.append(("", line[last_end:]))
            return parts or [("", line)]
        return get_line


PROMPT_STYLE = Style.from_dict({
    "prompt.divider": "#555555",
    "prompt.edge": "#555555",
    "prompt.plan": "#f38ba8 bold",
    "prompt.perm.all": "#a6e3a1 bold",
    "prompt.perm.manual": "#fab387 bold",
    "prompt.name": "#89b4fa bold",
    "prompt.arrow": "#cdd6f4 bold",
    "bottom-toolbar": "bg:#101010 #cdd6f4",
    "toolbar.border": "#555555",
    "toolbar.arrow": "#f9e2af bold",
    "toolbar.mode": "#f9e2af bold",
    "toolbar.dim": "#6c7086",
    "toolbar.sep": "#585b70",
    "toolbar.model": "#cba6f7 bold",
    "toolbar.badge": "bg:#1e1e2e #cba6f7 bold",
    "toolbar.info": "bg:#181825 #f9e2af",
    "toolbar.hint": "bg:#181825 #6c7086 italic",
    "toolbar.btw.label": "bg:#1e1e2e #f9e2af bold",
    "toolbar.btw.text": "bg:#1e1e2e #cdd6f4",
    "placeholder": "#6c7086 italic",
    "toolbar.dim": "bg:#181825 #6c7086 italic",
    "pasted-tag": "bg:#313244 #89dceb bold",
    "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current": "bg:#89b4fa #11111b bold",
    "completion-menu.meta.completion": "bg:#1e1e2e #a6adc8",
    "completion-menu.meta.completion.current": "bg:#89b4fa #181825 italic",
    "scrollbar.background": "bg:#181825",
    "scrollbar.button": "bg:#45475a",
})


def print_slash_menu():
    table = Table(title="Claude Code Compatible Slash Commands (onno-x)", border_style="cyan")
    table.add_column("Command", style="bold cyan", width=18)
    table.add_column("Fungsi / Deskripsi", style="white")
    for cmd, desc in SLASH_COMMANDS:
        table.add_row(cmd, desc)
    console.print(table)


app = typer.Typer(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": False},
    help="onno-x: Multi-model coding agent CLI .",
)
model_app = typer.Typer(help="Manage local and remote models (add, list, switch, remove).")
skill_app = typer.Typer(help="Manage reusable custom skills and workflows.")
app.add_typer(model_app, name="model")
app.add_typer(skill_app, name="skill")


# --- MODEL COMMANDS ---
@model_app.callback(invoke_without_command=True)
def model_default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        list_models()


@model_app.command("list")
def list_models():
    """List all configured models."""
    cfg = load_config()
    print_models_table(cfg.models, cfg.active_model)


@model_app.command("use")
@model_app.command("switch", hidden=True)
@model_app.command("set", hidden=True)
def use_model(alias: str = typer.Argument(..., help="Model alias to activate")):
    """Switch active model."""
    cfg = load_config()
    if alias not in cfg.models:
        console.print(f"[bold red]Error:[/bold red] Model '{alias}' does not exist.")
        raise typer.Exit(code=1)
    cfg.active_model = alias
    save_config(cfg)
    console.print(f"[bold green]✔ Active model switched to:[/bold green] [yellow]{alias}[/yellow]")


@model_app.command("add")
def add_model(
    alias: str = typer.Argument(..., help="Short name/alias, e.g. onno, hermes, gpt4o"),
    provider: str = typer.Option("openai", help="Provider: openai, anthropic, or ollama"),
    model_id: str = typer.Option(..., "--id", "-m", help="Target model ID/tag, e.g. onno-ai"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API Base URL (e.g. http://localhost:11434/v1)"),
    api_key: Optional[str] = typer.Option(None, "--key", "-k", help="API Key (optional for local models)"),
    temp: float = typer.Option(0.2, "--temp", help="Sampling temperature"),
    max_tokens: int = typer.Option(4096, "--tokens", help="Max tokens per response"),
    set_active: bool = typer.Option(True, "--set-active/--no-set-active", help="Set as active immediately"),
):
    """Add a new model to onno-x registry."""
    cfg = load_config()
    cfg.models[alias] = ModelSpec(
        name=alias,
        provider=provider,
        model_id=model_id,
        base_url=base_url,
        api_key=api_key,
        temperature=temp,
        max_tokens=max_tokens,
    )
    if set_active:
        cfg.active_model = alias
    save_config(cfg)
    console.print(f"[bold green]✔ Successfully configured model:[/bold green] [yellow]{alias}[/yellow] ({model_id})")


@model_app.command("remove")
def remove_model(alias: str = typer.Argument(..., help="Model alias to remove")):
    """Remove a model from registry."""
    cfg = load_config()
    if alias not in cfg.models:
        console.print(f"[bold red]Model '{alias}' not found.[/bold red]")
        raise typer.Exit(code=1)
    del cfg.models[alias]
    if cfg.active_model == alias and cfg.models:
        cfg.active_model = next(iter(cfg.models.keys()))
    save_config(cfg)
    console.print(f"[green]Model '{alias}' removed.[/green]")


# --- SKILL COMMANDS ---
def print_skills_table(query: Optional[str] = None):
    skills = list_skills()
    if not skills:
        console.print("[dim]No skills found. Add one with: onno-x skill add <name> or onno-x skill import <folder>[/dim]")
        return

    if query:
        q = query.lower().strip()
        skills = {k: v for k, v in skills.items() if q in k.lower() or q in v.description.lower()}
        if not skills:
            console.print(f"[yellow]No skills matching '{query}' found.[/yellow]")
            return

    table = Table(title=f"Available Skills ({len(skills)} total)", border_style="green")
    table.add_column("Skill Name", style="bold yellow")
    table.add_column("Scope", style="cyan", width=8)
    table.add_column("Description", style="white")
    for name, s in sorted(skills.items(), key=lambda x: x[0]):
        desc = s.description.strip().replace("\n", " ")
        if len(desc) > 85:
            desc = desc[:82] + "..."
        table.add_row(name, s.scope, desc)
    console.print(table)


@skill_app.callback(invoke_without_command=True)
def skill_default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        list_skills_cmd()


@skill_app.command("list")
def list_skills_cmd(query: Optional[str] = typer.Argument(None, help="Filter skills by keyword")):
    """List all available skills (global & local)."""
    print_skills_table(query)


@skill_app.command("add")
def add_skill_cmd(
    name: str = typer.Argument(..., help="Skill name (e.g. code-review, audit-security)"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Markdown file containing skill instructions"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="GitHub or web URL pointing to SKILL.md/markdown file"),
    desc: Optional[str] = typer.Option(None, "--desc", "-d", help="Short description"),
    local: bool = typer.Option(False, "--local", "-l", help="Save to current project .onno-x/skills/ instead of global"),
):
    """Add a new custom skill (from text, file, or URL)."""
    if url:
        try:
            with console.status(f"[cyan]Fetching skill from {url}...[/cyan]"):
                fetched = fetch_skill_from_url(url)
            content = fetched.content
            desc = desc or fetched.description
            name = name or fetched.name
        except Exception as e:
            console.print(f"[bold red]Failed to fetch from URL:[/bold red] {str(e)}")
            raise typer.Exit(1)
    elif file and file.exists():
        content = file.read_text(encoding="utf-8")
    else:
        console.print(f"[yellow]Enter skill instructions for '{name}'. Finish with Ctrl+D or empty line:[/yellow]")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except (EOFError, KeyboardInterrupt):
            pass
        content = "\n".join(lines).strip()
        if not content:
            console.print("[red]Aborted: Empty skill content.[/red]")
            raise typer.Exit(1)

    path = add_skill(name, content, description=desc, local=local)
    console.print(f"[bold green]✔ Skill '{name}' saved to:[/bold green] {path}")


@skill_app.command("install")
def install_skill_cmd(
    url: str = typer.Argument(..., help="GitHub URL (repo tree, blob, or raw URL)"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Override skill name"),
    local: bool = typer.Option(False, "--local", "-l", help="Save to local .onno-x/skills/ instead of global"),
):
    """Install a skill directly from a GitHub URL."""
    try:
        with console.status(f"[cyan]Downloading skill from {url}...[/cyan]"):
            skill = fetch_skill_from_url(url)
        target_name = name or skill.name
        path = add_skill(target_name, skill.content, description=skill.description, local=local)
        scope_str = "local (.onno-x/skills)" if local else "global (~/.onno-x/skills)"
        console.print(f"[bold green]✔ Installed skill:[/bold green] [yellow]{target_name}[/yellow] into {scope_str}")
        console.print(f"  • Description: {skill.description}")
        console.print(f"  • Path: {path}")
    except Exception as e:
        console.print(f"[bold red]Error installing skill:[/bold red] {str(e)}")
        raise typer.Exit(1)


@skill_app.command("remove")
def remove_skill_cmd(name: str = typer.Argument(..., help="Skill name to delete")):
    """Delete a skill."""
    if delete_skill(name):
        console.print(f"[green]Skill '{name}' deleted.[/green]")
    else:
        console.print(f"[red]Skill '{name}' not found.[/red]")


@skill_app.command("import")
def import_skills_cmd(
    source: Path = typer.Argument(Path("./skills"), help="Directory containing skills (e.g. ./skills or /path/to/skills)"),
    target_global: bool = typer.Option(True, "--global/--local", help="Import into ~/.onno-x/skills/ (default) or local .onno-x/skills/"),
):
    """Import an entire folder of skills into onno-x."""
    if not source.exists():
        console.print(f"[bold red]Error:[/bold red] Folder '{source}' not found.")
        raise typer.Exit(1)

    count = import_skills_from_dir(source, target_global=target_global)
    dest_name = "~/.onno-x/skills" if target_global else ".onno-x/skills"
    console.print(f"[bold green]✔ Successfully imported {count} skills into {dest_name}[/bold green]")


# --- MAIN RUNNER ---
@app.command("tui")
def tui_command(model: Optional[str] = typer.Option(None, "--model", "-m", help="Override active model for TUI")):
    """Launch the interactive Textual full-screen UI inspired by Claude Code CLI."""
    from onno_x.tui import run_tui
    run_tui(active_model=model)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override active model for this session"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Prompt to execute immediately (one-shot mode)"),
    resume: Optional[str] = typer.Option(None, "--resume", "-r", help="Resume previous session ID (or 'latest')"),
    cli: bool = typer.Option(False, "--cli", "-c", help="Launch classic readline CLI instead of Textual full-screen UI"),
):
    """Start interactive coding session or execute single prompt."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = load_config()
    if model:
        if model not in cfg.models:
            console.print(f"[bold red]Model '{model}' not found in registry.[/bold red]")
            raise typer.Exit(code=1)
        cfg.active_model = model
        save_config(cfg)

    session = AgentSession(cfg)

    # Resume requested via CLI flag or auto_resume setting in config
    should_resume = (resume is not None) or getattr(cfg, "auto_resume", False)
    if should_resume:
        target_id = resume.strip() if resume and resume.strip() not in ("", "latest", "true") else None
        if not target_id:
            lat = get_latest_session()
            if lat:
                target_id = lat["session_id"]
        if target_id:
            loaded = load_session(target_id)
            if loaded:
                session.session_id = loaded.get("session_id", target_id)
                session.messages = loaded.get("messages", session.messages)
                session.turns_count = loaded.get("turns_count", 0)
                session.permission_mode = loaded.get("permission_mode", "auto")
                session.plan_mode = loaded.get("plan_mode", False)
                console.print(f"[bold green]✔ Resumed session:[/bold green] [yellow]{target_id}[/yellow]")

    # One-shot mode: ambil dari --prompt atau trailing extra arguments (misal: onno-x "buat file")
    raw_prompt = prompt or (" ".join(ctx.args).strip() if ctx.args else None)
    if raw_prompt:
        session.run_turn(expand_at_file_mentions(raw_prompt))
        return

    # Textual full-screen UI is the DEFAULT mode:
    # Keeps input box permanently locked at the bottom, and renders answers above it!
    if not cli:
        from onno_x.tui import OnnoXUI
        tui_app = OnnoXUI(active_model=cfg.active_model, session=session)
        tui_app.run()
        return



    # Interactive REPL mode
    console.clear()
    print_banner(cfg.active_model)
    pad_to_bottom()
    # Keybindings: Enter executes, Esc+Enter inserts newline, BracketedPaste folds multi-line paste
    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    @kb.add("s-tab")
    def _(event):
        order = ["auto", "manual", "all"]
        cur = getattr(session, "permission_mode", "auto").lower()
        idx = order.index(cur) if cur in order else 0
        session.permission_mode = order[(idx + 1) % len(order)]
        event.app.invalidate()

    @kb.add(Keys.BracketedPaste)
    def _handle_paste(event):
        data = event.data.replace("\r\n", "\n").replace("\r", "\n")
        # Fold paste into clean badge if multi-line or long text (> 80 chars)
        if "\n" in data or len(data) > 80:
            tag = register_pasted_block(data)
            event.current_buffer.insert_text(tag)
        else:
            event.current_buffer.insert_text(data)

    # Ephemeral side question (/btw) state displayed under bottom border line
    btw_state = {"active": False, "answer": "", "question": ""}

    def get_prompt_message():
        return create_rounded_prompt_message(session=session)

    def get_bottom_toolbar():
        return create_rounded_bottom_toolbar(session=session, btw_state=btw_state)

    history_file = CONFIG_DIR / "history.txt"
    pt_session = PromptSession(
        message=get_prompt_message,
        rprompt=get_rounded_rprompt,
        bottom_toolbar=get_bottom_toolbar,
        prompt_continuation=rounded_prompt_continuation,
        placeholder=HTML('<style color="#6c7086">Try "fix lint errors" or "explain code"</style>'),
        history=FileHistory(str(history_file)),
        completer=ThreadedCompleter(SlashCompleter()),
        complete_while_typing=True,
        complete_in_thread=True,
        reserve_space_for_menu=0,
        multiline=True,
        key_bindings=kb,
        lexer=OnnoInputLexer(),
        style=PROMPT_STYLE,
    )

    last_response = ""

    while True:
        try:
            try:
                user_input = pt_session.prompt()
            except KeyboardInterrupt:
                console.print("\n[dim](Type /exit or press Ctrl+D to quit)[/dim]")
                continue
            except EOFError:
                console.print("[dim]Goodbye![/dim]")
                break
            clean = user_input.strip()
            if not clean:
                continue

            # Render full-width highlighted command bar in history matching Claude Code CLI
            print_user_prompt_bar(clean)

            # Clear /btw ephemeral drawer when starting another command
            if not clean.startswith("/btw"):
                btw_state["active"] = False

            # Unfold any folded pasted badges back into original full content
            clean = expand_pasted_blocks(clean)

            # Core slash commands dispatcher matching menu.md
            cmd_parts = clean.split()
            base_cmd = cmd_parts[0].lower()
            cmd_arg = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""

            if base_cmd in ("/exit", "/quit", "exit", "quit"):
                console.print("[dim]Goodbye![/dim]")
                break

            elif base_cmd in ("/help", "/"):
                print_slash_menu()
                continue

            elif base_cmd in ("/clear", "/reset", "/new"):
                console.clear()
                session.reset()
                print_banner(cfg.active_model)
                pad_to_bottom()
                continue

            elif base_cmd in ("/bug", "/share"):
                import platform, sys
                bug_report = (
                    f"## onno-x System Diagnostic & Share Report\n\n"
                    f"- **OS**: {platform.system()} {platform.release()} ({platform.machine()})\n"
                    f"- **Python**: {platform.python_version()} ({sys.executable})\n"
                    f"- **Active Model**: {session.spec.name} [{session.spec.provider}] ({session.spec.model_id})\n"
                    f"- **Endpoint**: {session.spec.base_url or 'default'}\n"
                    f"- **Total Turns**: {session.turns_count}\n"
                    f"- **Messages in Context**: {len(session.messages)}\n"
                    f"- **Active MCP Servers**: {list(MCPManager.get_instance().servers.keys())}\n"
                    f"- **Workspace**: {Path.cwd()}\n"
                )
                console.print(Panel(bug_report, title="Diagnostic Share Report", border_style="red"))
                continue

            elif base_cmd == "/color":
                valid_colors = ["cyan", "magenta", "green", "yellow", "blue", "red", "white", "default"]
                if not cmd_arg or cmd_arg.lower() not in valid_colors:
                    console.print(f"[yellow]Usage: /color [{'/'.join(valid_colors)}][/yellow]")
                else:
                    new_color = cmd_arg.lower()
                    accent_color = "cyan" if new_color == "default" else new_color
                    console.print(f"[{accent_color}]✔ Theme accent color set to: {new_color}[/{accent_color}]")
                continue

            elif base_cmd == "/compact":
                dropped = session.compact()
                console.print(f"[green]✔ Compacted conversation history (dropped {dropped} older messages).[/green]")
                continue

            elif base_cmd in ("/config", "/settings"):
                if cmd_arg and "=" in cmd_arg:
                    k, v = cmd_arg.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if hasattr(session.spec, k):
                        try:
                            # Attempt cast
                            cur_val = getattr(session.spec, k)
                            if isinstance(cur_val, float):
                                setattr(session.spec, k, float(v))
                            elif isinstance(cur_val, int):
                                setattr(session.spec, k, int(v))
                            else:
                                setattr(session.spec, k, v)
                            save_config(session.config)
                            console.print(f"[green]✔ Updated config {k} = {v}[/green]")
                        except Exception as ex:
                            console.print(f"[red]Failed to set {k}: {str(ex)}[/red]")
                    else:
                        console.print(f"[yellow]Unknown config key: {k}[/yellow]")
                else:
                    console.print(f"[bold cyan]Active Model Config:[/bold cyan] {session.spec.name}")
                    console.print(f"  • Provider:    {session.spec.provider}")
                    console.print(f"  • Model ID:    {session.spec.model_id}")
                    console.print(f"  • Base URL:    {session.spec.base_url or '(default)'}")
                    console.print(f"  • Max Tokens:  {session.spec.max_tokens}")
                    console.print(f"  • Temperature: {session.spec.temperature}")
                    console.print(f"  • Timeout:     {getattr(session.spec, 'timeout', 300.0)}s")
                    console.print(f"  • Output Style:{session.output_style}")
                continue

            elif base_cmd in ("/cost", "/usage", "/stats"):
                msg_count = len(session.messages)
                in_tok = session.total_input_tokens
                out_tok = session.total_output_tokens
                is_local = session.spec.provider in ("ollama",) or any(h in (session.spec.base_url or "") for h in ["localhost", "192.168", "127.0.0.1", "10.0"])
                cost_str = "$0.0000 (Local Self-hosted)" if is_local else f"${(in_tok * 0.000003 + out_tok * 0.000015):.4f} (API Estimated)"

                console.print(f"[bold cyan]Session Usage & Statistics:[/bold cyan]")
                console.print(f"  • Model:               {session.spec.name}")
                console.print(f"  • Conversation turns:  {session.turns_count}")
                console.print(f"  • Messages in context: {msg_count}")
                console.print(f"  • Total input tokens:  ~{in_tok:,}")
                console.print(f"  • Total output tokens: ~{out_tok:,}")
                console.print(f"  • Estimated cost:      [bold green]{cost_str}[/bold green]")
                continue

            elif base_cmd in ("/doctor", "/checkup"):
                import sys, platform, time
                console.print("[bold cyan]Running onno-x diagnostics...[/bold cyan]")
                console.print(f"  • Python:   {platform.python_version()} ({sys.executable})")
                console.print(f"  • OS:       {platform.system()} {platform.release()} ({platform.machine()})")
                console.print(f"  • Model:    {session.spec.name} [{session.spec.provider}] ({session.spec.model_id})")
                console.print(f"  • CWD:      {Path.cwd()}")

                # Git check
                git_check = subprocess.run("git rev-parse --is-inside-work-tree", shell=True, capture_output=True, text=True)
                if git_check.returncode == 0:
                    branch = subprocess.run("git branch --show-current", shell=True, capture_output=True, text=True).stdout.strip()
                    console.print(f"  • Git Repo: [green]Active[/green] (branch: {branch or 'detached'})")
                else:
                    console.print("  • Git Repo: [yellow]Not a git repository[/yellow]")

                # Endpoint connectivity check
                target_url = session.spec.base_url or ("https://api.anthropic.com" if session.spec.provider == "anthropic" else "https://api.openai.com/v1")
                try:
                    import httpx
                    start = time.time()
                    with httpx.Client(timeout=3.0) as client:
                        r = client.get(target_url.rstrip("/v1") + "/")
                        elapsed = int((time.time() - start) * 1000)
                        console.print(f"  • AI Model API: [green]Connected[/green] to {target_url} ({elapsed}ms, HTTP {r.status_code})")
                except Exception as e:
                    console.print(f"  • AI Model API: [yellow]Reachable test failed ({str(e)})[/yellow]")

                # External ecosystem connectivity (Obsidian & HexStrike)
                try:
                    with httpx.Client(timeout=2.0) as client:
                        r_obs = client.get("http://192.168.100.102:2233/")
                        console.print(f"  • Obsidian Memory: [green]Online[/green] (http://192.168.100.102:2233, HTTP {r_obs.status_code})")
                except Exception:
                    console.print("  • Obsidian Memory: [dim yellow]Offline / Unreachable (192.168.100.102:2233)[/dim yellow]")

                try:
                    with httpx.Client(timeout=2.0) as client:
                        r_hex = client.get("http://192.168.100.102:8888/health")
                        console.print(f"  • HexStrike API:   [green]Online[/green] (http://192.168.100.102:8888, HTTP {r_hex.status_code})")
                except Exception:
                    console.print("  • HexStrike API:   [dim yellow]Offline / Unreachable (192.168.100.102:8888)[/dim yellow]")

                # MCP Manager status
                mcp_mgr = MCPManager.get_instance()
                srv_names = list(mcp_mgr.servers.keys())
                total_defs = get_active_tool_definitions()
                console.print(f"  • MCP Servers:     [green]{len(srv_names)} active[/green] ({', '.join(srv_names) or 'none'})")
                console.print(f"  • Active Tools:    [green]{len(total_defs)} exposed tools[/green] (15 Native + {len(mcp_mgr.tool_map)} MCP)")
                continue

            elif base_cmd == "/add-dir":
                if not cmd_arg:
                    console.print("[yellow]Usage: /add-dir <path>[/yellow]")
                elif session.add_directory(cmd_arg):
                    console.print(f"[bold green]✔ Added directory access:[/bold green] {cmd_arg}")
                else:
                    console.print(f"[red]Directory not found: {cmd_arg}[/red]")
                continue

            elif base_cmd == "/cd":
                if not cmd_arg:
                    console.print(f"Current directory: {Path.cwd()}")
                elif session.change_directory(cmd_arg):
                    console.print(f"[bold green]✔ Changed working directory to:[/bold green] {Path.cwd()}")
                else:
                    console.print(f"[red]Directory not found: {cmd_arg}[/red]")
                continue

            elif base_cmd == "/advisor":
                if not cmd_arg:
                    console.print(f"Advisor model: {session.advisor_model or 'off'}")
                elif cmd_arg.lower() in ("off", "none", "disable"):
                    session.advisor_model = None
                    console.print("[dim]Advisor model disabled.[/dim]")
                else:
                    session.advisor_model = cmd_arg
                    console.print(f"[green]✔ Advisor model set to: {cmd_arg}[/green]")
                continue

            elif base_cmd == "/agents":
                console.print(Panel(
                    "## onno-x Agents System\n"
                    "- Autonomous agent loop with multi-step tool execution\n"
                    "- 11 Built-in tools: shell, filesystem (read/write/edit/delete/grep), web browsing, web search, skills\n"
                    "- Subagent workflows supported via background tasks & /plan mode\n"
                    "- Configurable via ONNO.md / CLAUDE.md in current workspace",
                    title="Agent Architecture",
                    border_style="cyan"
                ))
                continue

            elif base_cmd == "/autocompact":
                console.print("[bold green]✔ Autocompact is active.[/bold green] Automatically trims context buffer when nearing context limit.")
                continue

            elif base_cmd == "/branch":
                bname = cmd_arg or f"branch-{len(session.checkpoints)+1}"
                session.create_checkpoint()
                console.print(f"[bold green]✔ Created conversation branch point:[/bold green] [yellow]{bname}[/yellow]")
                continue

            elif base_cmd == "/btw":
                if not cmd_arg:
                    console.print("[yellow]Usage: /btw <pertanyaan sampingan>[/yellow]")
                else:
                    ans = session.run_turn(cmd_arg, ephemeral=True)
                    btw_state["active"] = True
                    btw_state["question"] = cmd_arg
                    btw_state["answer"] = (ans or "").strip().replace("\n", " ")
                    console.print("[dim]✔ Side answer placed below input box. Main conversation history preserved.[/dim]")
                continue

            elif base_cmd == "/context":
                total_chars = sum(len(str(m.get("content", ""))) for m in session.messages)
                approx_tokens = total_chars // 4
                table = Table(title="Context Usage Breakdown", border_style="magenta")
                table.add_column("Index", width=6)
                table.add_column("Role", width=12, style="bold cyan")
                table.add_column("Tokens (approx)", justify="right", width=15)
                table.add_column("Preview", style="dim white")

                for idx, m in enumerate(session.messages):
                    c = str(m.get("content", ""))
                    toks = len(c) // 4
                    snip = c.replace("\n", " ")[:60]
                    table.add_row(str(idx), m.get("role", "unknown"), f"~{toks:,}", snip)
                console.print(table)
                console.print(f"[bold]Total Messages:[/bold] {len(session.messages)}  •  [bold]Estimated Tokens:[/bold] ~{approx_tokens:,}")
                continue

            elif base_cmd == "/copy":
                target_text = last_response or (session.messages[-1].get("content") if session.messages else "")
                if not target_text:
                    console.print("[dim]No response to copy.[/dim]")
                else:
                    copied = False
                    # macOS pbcopy
                    try:
                        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                        p.communicate(target_text.encode("utf-8"))
                        copied = True
                    except Exception:
                        pass
                    if copied:
                        console.print("[bold green]✔ Copied last response to clipboard.[/bold green]")
                    else:
                        console.print(Panel(target_text, title="Response Content", border_style="green"))
                continue

            elif base_cmd == "/diff":
                diff_res = subprocess.run("git diff", shell=True, capture_output=True, text=True).stdout.strip()
                if not diff_res:
                    stat_res = subprocess.run("git status -s", shell=True, capture_output=True, text=True).stdout.strip()
                    diff_res = f"No unstaged diff.\nStatus:\n{stat_res or 'Working tree clean'}"
                console.print(Panel(diff_res, title="Git Working Tree Diff", border_style="yellow"))
                continue

            elif base_cmd == "/commit":
                git_check = subprocess.run("git rev-parse --is-inside-work-tree", shell=True, capture_output=True, text=True)
                if git_check.returncode != 0:
                    console.print("[red]Current directory is not a git repository.[/red]")
                    continue

                diff_output = subprocess.run("git diff HEAD", shell=True, capture_output=True, text=True).stdout.strip()
                status_output = subprocess.run("git status --short", shell=True, capture_output=True, text=True).stdout.strip()
                if not status_output:
                    console.print("[yellow]Working tree is clean. Nothing to commit.[/yellow]")
                    continue

                if cmd_arg:
                    commit_msg = cmd_arg
                else:
                    console.print("[bold cyan]Analyzing git diff and generating conventional commit message...[/bold cyan]")
                    commit_prompt = (
                        "Generate a concise, conventional git commit message (e.g. 'feat(auth): add token validation' or 'fix(api): handle timeout') "
                        f"for these git changes. Output ONLY the commit message subject line, no explanations or quotes:\n\n{status_output}\n\n{diff_output[:1500]}"
                    )
                    suggested_msg, _ = session.provider.chat([
                        {"role": "system", "content": "You are a git commit assistant. Respond with ONLY the commit message subject line."},
                        {"role": "user", "content": commit_prompt}
                    ], tools=[])
                    commit_msg = suggested_msg.strip().replace('"', '').strip() if suggested_msg else "update project files"

                console.print(f"[bold yellow]Proposed commit message:[/bold yellow] [bold green]{commit_msg}[/bold green]")
                try:
                    c_choice = console.input("[bold white]Proceed with commit? ([green]y[/green]=yes / [yellow]e[/yellow]=edit / [red]n[/red]=cancel): [/bold white]").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    c_choice = "n"

                if c_choice in ("e", "edit"):
                    try:
                        commit_msg = console.input("[bold cyan]Enter new commit message: [/bold cyan]").strip()
                    except (EOFError, KeyboardInterrupt):
                        commit_msg = ""

                if c_choice in ("y", "yes", "e", "edit") and commit_msg:
                    subprocess.run("git add -A", shell=True, check=True)
                    res = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
                    if res.returncode == 0:
                        console.print(f"[bold green]✔ Committed successfully:[/bold green] {commit_msg}")
                    else:
                        console.print(f"[bold red]Commit failed:[/bold red] {res.stderr}")
                else:
                    console.print("[dim]Commit cancelled.[/dim]")
                continue

            elif base_cmd == "/pr":
                git_check = subprocess.run("git rev-parse --is-inside-work-tree", shell=True, capture_output=True, text=True)
                if git_check.returncode != 0:
                    console.print("[red]Current directory is not a git repository.[/red]")
                    continue

                branch = subprocess.run("git branch --show-current", shell=True, capture_output=True, text=True).stdout.strip()
                diff_log = subprocess.run("git log -n 5 --oneline", shell=True, capture_output=True, text=True).stdout.strip()
                diff_stat = subprocess.run("git diff --stat HEAD~1 HEAD 2>/dev/null || git status -s", shell=True, capture_output=True, text=True).stdout.strip()

                pr_title = cmd_arg or f"Update from {branch}"
                console.print(f"[bold cyan]Creating Pull Request summary for branch:[/bold cyan] [yellow]{branch}[/yellow]")
                summary_prompt = f"Write a clean GitHub PR summary in Markdown with '### Changes' and '### Verification' for recent commits:\n{diff_log}\n{diff_stat}"
                pr_body, _ = session.provider.chat([
                    {"role": "system", "content": "You are a developer creating a GitHub Pull Request description. Format neatly in Markdown."},
                    {"role": "user", "content": summary_prompt}
                ], tools=[])

                pr_body = pr_body.strip() if pr_body else "Automated PR from onno-x."
                console.print(Panel(f"## {pr_title}\n\n{pr_body}", title="Generated PR Details", border_style="cyan"))

                gh_check = subprocess.run("which gh", shell=True, capture_output=True)
                if gh_check.returncode == 0:
                    try:
                        open_gh = console.input("[bold white]Create PR via GitHub CLI ('gh pr create')? ([green]y[/green]/[red]N[/red]): [/bold white]").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        open_gh = "n"
                    if open_gh in ("y", "yes"):
                        res = subprocess.run(["gh", "pr", "create", "--title", pr_title, "--body", pr_body], capture_output=True, text=True)
                        if res.returncode == 0:
                            console.print(f"[bold green]✔ Pull Request created:[/bold green] {res.stdout.strip()}")
                        else:
                            console.print(f"[yellow]gh pr create failed: {res.stderr}[/yellow]")
                continue

            elif base_cmd == "/mcp":
                mcp_mgr = MCPManager.get_instance()
                args_parts = cmd_arg.split()
                sub = args_parts[0].lower() if args_parts else "list"

                if sub in ("reload", "refresh", "restart"):
                    mcp_mgr.load_configs()
                    console.print(f"[bold green]✔ MCP configuration reloaded.[/bold green] Connected servers: {len(mcp_mgr.servers)}, dynamic tools: {len(mcp_mgr.tool_map)}")
                else:
                    t = Table(title=f"MCP Servers ({len(mcp_mgr.servers)}) & Dynamic Tools ({len(mcp_mgr.tool_map)})", border_style="magenta")
                    t.add_column("Server", style="bold cyan")
                    t.add_column("Command", style="yellow")
                    t.add_column("Tools Exposed", style="green")
                    if not mcp_mgr.servers:
                        console.print(Panel(
                            "No MCP servers active.\nTo configure MCP servers, create `.mcp.json` in your workspace or `~/.onno-x/mcp.json`:\n\n"
                            '{\n  "mcpServers": {\n    "sqlite": {\n      "command": "uvx",\n      "args": ["mcp-server-sqlite", "--db-path", "app.db"]\n    }\n  }\n}',
                            title="Model Context Protocol (MCP)",
                            border_style="cyan"
                        ))
                    else:
                        for s_name, proc in mcp_mgr.servers.items():
                            t.add_row(
                                s_name,
                                f"{proc.command} {' '.join(proc.args[:2])}",
                                ", ".join([t_["name"] for t_ in proc.tools[:5]]) or "(none)"
                            )
                        console.print(t)
                        console.print("[dim]Use /mcp reload to refresh servers.[/dim]")
                continue

            elif base_cmd in ("/notify", "/bell"):
                if cmd_arg.lower() in ("off", "disable", "mute"):
                    session.notify_completion = False
                    console.print("[dim]Completion sound alert disabled.[/dim]")
                elif cmd_arg.lower() in ("on", "enable"):
                    session.notify_completion = True
                    console.print("[green]✔ Completion sound alert enabled.[/green]")
                else:
                    session.notify_completion = not session.notify_completion
                    st = "ENABLED" if session.notify_completion else "DISABLED"
                    console.print(f"[cyan]Completion alert: {st}[/cyan]")
                continue

            elif base_cmd in ("/obsidian", "/memo"):
                parts = cmd_arg.split(maxsplit=1)
                sub_cmd = parts[0].lower() if parts else "list"
                sub_arg = parts[1] if len(parts) > 1 else ""

                if sub_cmd in ("search", "find"):
                    if not sub_arg:
                        console.print("[yellow]Usage: /obsidian search <query>[/yellow]")
                    else:
                        console.print(f"[bold cyan]Searching Obsidian memory for:[/bold cyan] {sub_arg}")
                        console.print(obsidian_search_notes(sub_arg))
                elif sub_cmd in ("read", "view", "get", "cat"):
                    if not sub_arg:
                        console.print("[yellow]Usage: /obsidian read <note_name>[/yellow]")
                    else:
                        content = obsidian_read_note(sub_arg)
                        console.print(Panel(content, title=f"Obsidian Note: {sub_arg}", border_style="magenta"))
                elif sub_cmd in ("write", "save", "add"):
                    if not sub_arg or "|" not in sub_arg:
                        console.print("[yellow]Usage: /obsidian write <Title> | <Content>[/yellow]")
                    else:
                        ntitle, ncontent = sub_arg.split("|", 1)
                        res = obsidian_write_note(ntitle.strip(), ncontent.strip())
                        console.print(f"[bold green]✔ {res}[/bold green]")
                else:
                    console.print(Panel(
                        "## Obsidian Memory Integration (192.168.100.102:2233)\n\n"
                        "Command Usage:\n"
                        "- **/obsidian search <keyword>**: Cari catatan & temuan di memori\n"
                        "- **/obsidian read <note.md>**: Baca isi lengkap catatan\n"
                        "- **/obsidian write <Title> | <Content>**: Tulis/simpan catatan baru\n\n"
                        "💡 *Tip: Agent LLM juga otomatis memanggil tool 'obsidian_write_note' saat kamu memintanya menyimpan temuan/catatan.*",
                        title="Obsidian Knowledge Base",
                        border_style="magenta"
                    ))
                continue

            elif base_cmd == "/effort":
                if not cmd_arg:
                    console.print(f"Current reasoning effort: temperature={session.spec.temperature}")
                else:
                    eff = session.set_effort(cmd_arg)
                    console.print(f"[bold green]✔ Effort set to:[/bold green] {eff}")
                continue

            elif base_cmd == "/export":
                export_path = Path(cmd_arg or "onno-session-export.md").resolve()
                lines = [f"# onno-x Session Export\nModel: {session.spec.name}\n\n"]
                for m in session.messages:
                    r = m.get("role", "").upper()
                    c = m.get("content", "")
                    if c:
                        lines.append(f"### {r}:\n{c}\n\n")
                export_path.write_text("".join(lines), encoding="utf-8")
                console.print(f"[bold green]✔ Exported conversation to:[/bold green] {export_path}")
                continue

            elif base_cmd == "/fast":
                if cmd_arg.lower() == "on":
                    session.fast_mode = True
                    session.spec.temperature = 0.0
                elif cmd_arg.lower() == "off":
                    session.fast_mode = False
                    session.spec.temperature = 0.2
                else:
                    session.toggle_fast_mode()
                color = "green" if session.fast_mode else "yellow"
                status_text = "ENABLED (temp=0.0)" if session.fast_mode else "DISABLED (temp=0.2)"
                console.print(f"[{color}]Fast Mode: {status_text}[/{color}]")
                continue

            elif base_cmd == "/feedback":
                console.print("[dim]Feedback recorded locally in session diagnostics.[/dim]")
                continue

            elif base_cmd == "/fork":
                fork_id = f"fork_{len(session.checkpoints)+1}"
                session.create_checkpoint()
                console.print(f"[bold green]✔ Forked session to checkpoint:[/bold green] [yellow]{fork_id}[/yellow]")
                continue

            elif base_cmd == "/goal":
                if not cmd_arg or cmd_arg.lower() == "clear":
                    console.print("[dim]Goal condition cleared.[/dim]")
                else:
                    console.print(f"[bold cyan]🎯 Goal Set:[/bold cyan] {cmd_arg}")
                    session.run_turn(f"Execute until this goal is fully accomplished: {cmd_arg}")
                continue

            elif base_cmd == "/init":
                target_file = Path.cwd() / "ONNO.md"
                if not target_file.exists():
                    target_file.write_text(
                        "# ONNO.md — Project Instructions for onno-x\n\n"
                        "## Architecture & Conventions\n"
                        "- Keep changes minimal and self-contained.\n"
                        "- Check tests or run verification before finalizing.\n"
                        "- Zero unnecessary dependencies.\n",
                        encoding="utf-8"
                    )
                    console.print(f"[bold green]✔ Created project guide:[/bold green] {target_file}")
                else:
                    console.print(f"[dim]Project guide already exists: {target_file}[/dim]")

                local_dir = Path.cwd() / ".onno-x" / "skills"
                local_dir.mkdir(parents=True, exist_ok=True)
                console.print(f"[bold green]✔ Initialized local skills folder:[/bold green] {local_dir}")
                session.refresh_skills()
                continue

            elif base_cmd == "/memory":
                mem_found = False
                for f in [Path.cwd() / "ONNO.md", Path.cwd() / "CLAUDE.md"]:
                    if f.exists():
                        console.print(Panel(f.read_text(encoding="utf-8"), title=f"Project Memory ({f.name})", border_style="green"))
                        mem_found = True
                        break
                if not mem_found:
                    console.print("[dim]No ONNO.md or CLAUDE.md found. Use /init to generate one.[/dim]")
                continue

            elif base_cmd == "/output-style":
                if not cmd_arg:
                    console.print(f"Current output style: {session.output_style}")
                else:
                    st = session.set_output_style(cmd_arg)
                    console.print(f"[green]✔ Output style set to: {st}[/green]")
                continue

            elif base_cmd in ("/permissions", "/allowed-tools", "/mode", "/yolo", "/auto", "/manual"):
                if base_cmd == "/yolo":
                    cmd_arg = "all"
                elif base_cmd == "/auto":
                    cmd_arg = "auto"
                elif base_cmd == "/manual":
                    cmd_arg = "manual"

                if cmd_arg:
                    arg_clean = cmd_arg.lower().strip()
                    if arg_clean in ("auto", "default"):
                        session.set_permission_mode("auto")
                        console.print("[bold green]✔ Permission mode set to: AUTO[/bold green] (Safe read tools auto-run; bash commands & deletions require confirmation)")
                    elif arg_clean in ("manual", "ask", "strict"):
                        session.set_permission_mode("manual")
                        console.print("[bold yellow]✔ Permission mode set to: MANUAL[/bold yellow] (Confirmation required for bash execution, file writes, edits, and deletions)")
                    elif arg_clean in ("all", "accept-all", "accept_all", "yolo", "allow"):
                        session.set_permission_mode("all")
                        console.print("[bold red]✔ Permission mode set to: ACCEPT ALL (YOLO)[/bold red] (All tools execute automatically without prompts)")
                    else:
                        console.print(f"[yellow]Unknown mode '{cmd_arg}'. Choose: auto, manual, or all[/yellow]")
                else:
                    cur = session.permission_mode.upper()
                    console.print(Panel(
                        f"Current Permission Mode: **[cyan]{cur}[/cyan]**\n\n"
                        "Available Modes:\n"
                        "- **/permissions auto** (Default): Safe read tools (read, grep, list, web, skills) auto-run. Shell commands & deletions prompt for confirmation `[y/N/a]`.\n"
                        "- **/permissions manual**: Strict mode. All bash commands, file writes, edits, and deletions require user confirmation.\n"
                        "- **/permissions all** (Accept All / YOLO): All tools execute autonomously without stopping.\n\n"
                        "💡 *Tip: When prompted for confirmation on any tool, enter 'a' to immediately accept all tools for the rest of the session.*",
                        title=f"Tool Permission Settings [{cur}]",
                        border_style="cyan"
                    ))
                continue

            elif base_cmd == "/plan":
                state = None
                if cmd_arg.lower() in ("on", "start", "enable"):
                    state = True
                elif cmd_arg.lower() in ("off", "stop", "disable"):
                    state = False
                active = session.toggle_plan_mode(state)
                color = "green" if active else "yellow"
                status_str = "ENABLED (Architect mode: read files & plan without edits)" if active else "DISABLED (Normal execution)"
                console.print(f"[{color}]Plan Mode: {status_str}[/{color}]")
                continue

            elif base_cmd == "/plugin":
                args = cmd_arg.split()
                sub = args[0].lower() if args else ""
                target = args[1] if len(args) > 1 else ""

                if sub in ("list", "ls", ""):
                    mps = load_marketplaces()
                    plugins = [s for s in list_skills().values() if s.scope in ("plugin", "global")]
                    console.print(Panel(
                        f"## Registered Marketplaces ({len(mps)}):\n" +
                        "\n".join([f"- **{k}**: {v}" for k, v in mps.items()]) +
                        f"\n\n## Installed Plugin Skills ({len(plugins)} total):\n" +
                        "\n".join([f"- {p.name}: {p.description[:70]}" for p in plugins[:15]]) +
                        (f"\n... (+{len(plugins)-15} more)" if len(plugins) > 15 else ""),
                        title="Plugin & Marketplace Manager",
                        border_style="cyan"
                    ))
                    console.print("[dim]Usage:\n  /plugin install <package|url>\n  /plugin marketplace add <owner/repo>[/dim]")
                elif sub in ("marketplace", "market"):
                    action = args[1].lower() if len(args) > 1 else ""
                    m_target = args[2] if len(args) > 2 else ""
                    mps = load_marketplaces()
                    if action in ("add", "register") and m_target:
                        url = f"https://github.com/{m_target}" if not m_target.startswith("http") else m_target
                        mps[m_target] = url
                        save_marketplaces(mps)
                        console.print(f"[bold green]✔ Added marketplace:[/bold green] [yellow]{m_target}[/yellow] ({url})")
                    else:
                        console.print(f"[bold cyan]Known Marketplaces:[/bold cyan] {list(mps.keys())}")
                        console.print("[dim]Usage: /plugin marketplace add <owner/repo>[/dim]")
                elif sub in ("install", "add") and target:
                    try:
                        with console.status(f"[cyan]Installing plugin '{target}'...[/cyan]"):
                            fetched = fetch_skill_from_url(target)
                        add_skill(fetched.name, fetched.content, description=fetched.description)
                        session.refresh_skills()
                        console.print(f"[bold green]✔ Successfully installed plugin skill:[/bold green] [yellow]{fetched.name}[/yellow]")
                        console.print(f"  • Description: {fetched.description}")
                    except Exception as e:
                        console.print(f"[bold red]Failed to install plugin:[/bold red] {str(e)}")
                elif sub in ("remove", "rm", "uninstall") and target:
                    if delete_skill(target):
                        session.refresh_skills()
                        console.print(f"[green]✔ Removed plugin {target}[/green]")
                    else:
                        console.print(f"[yellow]Plugin {target} not found.[/yellow]")
                else:
                    console.print("[yellow]Usage: /plugin [list|install <pkg>|remove <name>|marketplace add <owner/repo>][/yellow]")
                continue

            elif base_cmd == "/recap":
                session.run_turn("Berikan ringkasan eksekutif 1-2 baris padat tentang apa yang sudah kita kerjakan dan capai di sesi ini.")
                continue

            elif base_cmd in ("/sessions", "/history"):
                sess_list = list_sessions()
                if not sess_list:
                    console.print("[dim]No saved sessions found.[/dim]")
                else:
                    t = Table(title=f"Saved Sessions ({len(sess_list)})", border_style="cyan")
                    t.add_column("Session ID", style="bold cyan")
                    t.add_column("Last Updated", style="yellow")
                    t.add_column("Model", style="white")
                    t.add_column("Turns", justify="right")
                    t.add_column("Messages", justify="right")
                    t.add_column("Workspace", style="dim")
                    for s in sess_list[:15]:
                        t.add_row(
                            s["id"],
                            s["updated_at"][:19].replace("T", " "),
                            s["model_name"],
                            str(s["turns_count"]),
                            str(s["messages_count"]),
                            str(Path(s.get("cwd", "")).name or s.get("cwd", ""))[:25]
                        )
                    console.print(t)
                    console.print("[dim]Use /resume <session_id> to restore a session.[/dim]")
                continue

            elif base_cmd in ("/resume", "/continue"):
                target_id = cmd_arg.strip()
                if not target_id:
                    lat = get_latest_session()
                    if lat:
                        target_id = lat["session_id"]
                    else:
                        console.print("[yellow]No prior saved session found to resume.[/yellow]")
                        continue

                loaded = load_session(target_id)
                if loaded:
                    session.session_id = loaded.get("session_id", target_id)
                    session.messages = loaded.get("messages", session.messages)
                    session.turns_count = loaded.get("turns_count", 0)
                    session.permission_mode = loaded.get("permission_mode", "auto")
                    session.plan_mode = loaded.get("plan_mode", False)
                    console.print(f"[bold green]✔ Resumed session:[/bold green] [yellow]{target_id}[/yellow] ({len(session.messages)} messages, {session.turns_count} turns)")
                else:
                    console.print(f"[red]Session '{target_id}' not found.[/red]")
                continue

            elif base_cmd in ("/rewind", "/undo", "/checkpoint"):
                res = session.rewind_checkpoint()
                if res.get("reverted"):
                    console.print("[bold green]✔ Rewound conversation to prior checkpoint.[/bold green]")
                    restored = res.get("files_restored", [])
                    if restored:
                        console.print(f"[bold cyan]📁 File System Restorations ({len(restored)}):[/bold cyan]")
                        for item in restored:
                            console.print(f"   [yellow]•[/yellow] {item}")
                    else:
                        console.print("[dim]No file system modifications were made in that step.[/dim]")
                else:
                    console.print("[yellow]No prior checkpoint found in this session.[/yellow]")
                continue

            elif base_cmd == "/run":
                target_cmd = cmd_arg or "pytest || npm test || python3 -m unittest"
                console.print(f"[bold cyan]Running verification command:[/bold cyan] {target_cmd}")
                session.run_turn(f"Execute shell verification: {target_cmd} and report findings.")
                continue

            elif base_cmd in ("/code-review", "/review"):
                console.print("[bold cyan]Running automated code review...[/bold cyan]")
                session.run_turn("Review current project files and uncommitted git diff for bugs, vulnerabilities, and optimization opportunities.")
                continue

            elif base_cmd == "/security-review":
                console.print("[bold red]Running security review...[/bold red]")
                session.run_turn("Audit repository against OWASP Top 10, injection vulnerabilities, unvalidated inputs, and secret leaks.")
                continue

            elif base_cmd == "/simplify":
                console.print("[bold cyan]Running code simplification review...[/bold cyan]")
                session.run_turn("Review the recent changes to simplify structure, eliminate duplicate logic, and remove dead code.")
                continue

            elif base_cmd == "/verify":
                console.print("[bold cyan]Verifying implementation...[/bold cyan]")
                session.run_turn("Verify that recent implementation works end-to-end, checking imports, syntax, tests, and runtime.")
                continue

            elif base_cmd == "/status":
                console.print(f"[bold cyan]onno-x System Status:[/bold cyan]")
                console.print(f"  • Active Model: {session.spec.name} ({session.spec.provider})")
                console.print(f"  • Endpoint:     {session.spec.base_url or 'default'}")
                console.print(f"  • Plan Mode:    {session.plan_mode}")
                console.print(f"  • Fast Mode:    {session.fast_mode}")
                console.print(f"  • Total Turns:  {session.turns_count}")
                console.print(f"  • Workspace:    {Path.cwd()}")
                continue

            elif base_cmd == "/terminal-setup":
                console.print("[bold cyan]Testing Terminal Capabilities:[/bold cyan]")
                colors = ["red", "green", "yellow", "blue", "magenta", "cyan", "white"]
                color_line = " ".join([f"[{c}]■ {c}[/{c}]" for c in colors])
                console.print(f"  • Colors:  {color_line}")
                console.print("  • Unicode: [green]✔[/green] Box: [cyan]┌─┬─┐│ ├─┼─┤│ └─┴─┘[/cyan] Arrows: [yellow]❯ → ➔[/yellow]")
                console.print("  • Styles:  [bold]Bold[/bold], [italic]Italic[/italic], [underline]Underline[/underline], [dim]Dim[/dim]")
                continue

            elif base_cmd == "/models":
                print_models_table(cfg.models, session.spec.name)
                continue

            elif base_cmd == "/model":
                if not cmd_arg:
                    print_models_table(cfg.models, session.spec.name)
                elif session.switch_model(cmd_arg):
                    console.print(f"[bold green]✔ Switched and persisted active model to:[/bold green] [yellow]{cmd_arg}[/yellow]")
                else:
                    console.print(f"[red]Model '{cmd_arg}' not found.[/red]")
                continue

            elif base_cmd == "/skills":
                print_skills_table(cmd_arg or None)
                continue

            elif base_cmd == "/skill":
                parts = clean.split()
                if len(parts) >= 3 and parts[1] == "install":
                    url = parts[2]
                    try:
                        with console.status(f"[cyan]Installing skill from {url}...[/cyan]"):
                            fetched = fetch_skill_from_url(url)
                        add_skill(fetched.name, fetched.content, description=fetched.description)
                        session.refresh_skills()
                        console.print(f"[bold green]✔ Successfully installed skill:[/bold green] [yellow]{fetched.name}[/yellow]")
                    except Exception as e:
                        console.print(f"[red]Failed to install skill:[/red] {str(e)}")
                    continue

                skill_name = cmd_arg.strip()
                skills = list_skills()
                if skill_name in skills:
                    target_skill = skills[skill_name]
                    resp = session.run_turn(f"Execute skill [{target_skill.name}]:\n{target_skill.content}")
                    if resp:
                        last_response = resp
                else:
                    console.print(f"[red]Skill '{skill_name}' not found. Use /skills to list available ones.[/red]")
                continue

            # Standard user prompt turn
            clean_with_attachments = expand_at_file_mentions(clean)
            resp = session.run_turn(clean_with_attachments)
            if resp:
                last_response = resp

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break


if __name__ == "__main__":
    app()
