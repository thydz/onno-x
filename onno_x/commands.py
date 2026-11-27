"""Shared logic for the utility slash commands (/test, /grep, /find, /log, ...).

Both the REPL (main.py) and the Textual UI (tui.py) call these; keeping the
shell/git work here means the two front-ends cannot drift apart.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from onno_x.session import estimate_tokens

# Directories that never contain project source worth searching.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
             ".ruff_cache", "dist", "build", ".idea", ".vscode", "target"}

OUTPUT_LIMIT = 6000


def expand_alias(cfg: Any, text: str) -> str:
    """Rewrite a leading /alias into its stored command template.

    `name rest` with alias `name -> "/test pytest -x"` becomes
    `/test pytest -x rest`.
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return text
    parts = stripped.split(maxsplit=1)
    name = parts[0][1:]
    aliases = getattr(cfg, "aliases", {}) or {}
    target = aliases.get(name)
    if not target:
        return text
    rest = parts[1] if len(parts) > 1 else ""
    return f"{target} {rest}".strip()


def run_shell_capture(
    cmd: str,
    cwd: Optional[Path] = None,
    timeout: int = 900,
    cancel_event: Any = None,
) -> Tuple[int, str]:
    """Run a command, return (exit code, combined output). Never raises.

    If ``cancel_event`` is provided and gets set while the command is running,
    the process is terminated and exit code 130 is returned.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        return 127, f"Gagal menjalankan command: {exc}"

    start = time.monotonic()
    cancelled = False
    timed_out = False
    while proc.poll() is None:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            cancelled = True
            try:
                proc.terminate()
            except Exception:
                pass
            break
        if time.monotonic() - start > timeout:
            timed_out = True
            try:
                proc.kill()
            except Exception:
                pass
            break
        time.sleep(0.2)

    try:
        stdout, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            stdout, _ = proc.communicate(timeout=5)
        except Exception:
            stdout = ""

    output = (stdout or "").strip()
    if len(output) > OUTPUT_LIMIT:
        output = output[:OUTPUT_LIMIT] + "\n... (output dipotong)"
    if cancelled:
        return 130, (output + "\n⚡ Dibatalkan oleh user").strip()
    if timed_out:
        return 124, (output or f"Command timeout setelah {timeout}s: {cmd}").strip()
    return proc.returncode, output


def detect_test_command(cwd: Optional[Path] = None) -> Optional[str]:
    """Pick the most specific test runner the project actually configures."""
    root = Path(cwd or Path.cwd())
    py = f'"{sys.executable}"' if " " in sys.executable else sys.executable

    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "tox.ini").exists():
        if shutil.which("pytest"):
            return "pytest -q"
    if (root / "package.json").exists():
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            script = str((data.get("scripts") or {}).get("test") or "").strip()
            # npm init writes a placeholder that always exits 1. Treating it as
            # a real test command makes auto-verify fail on every JS project.
            placeholder = "no test specified" in script.lower()
            if script and not placeholder:
                return "npm test --silent"
        except (OSError, ValueError):
            pass
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test -q"
    if (root / "Makefile").exists():
        try:
            if "test:" in (root / "Makefile").read_text(encoding="utf-8", errors="replace"):
                return "make test"
        except OSError:
            pass
    if (root / "tests").is_dir() or (root / "test").is_dir():
        target = "tests" if (root / "tests").is_dir() else "test"
        if shutil.which("pytest"):
            return f"pytest -q {target}"
        return f"{py} -m unittest discover -s {target}"
    return None


def _has_local_npm_bin(root: Path, name: str) -> bool:
    """True when a package is installed in node_modules/.bin."""
    bin_dir = root / "node_modules" / ".bin"
    return any(
        (bin_dir / f"{name}{suffix}").exists()
        for suffix in ("", ".cmd", ".ps1", ".exe")
    )


def detect_lint_command(cwd: Optional[Path] = None) -> Optional[str]:
    root = Path(cwd or Path.cwd())
    if (root / "ruff.toml").exists() or (root / ".ruff.toml").exists() or (root / "pyproject.toml").exists():
        if shutil.which("ruff"):
            return "ruff check ."
    if (root / "go.mod").exists():
        return "gofmt -l ."
    if (root / "Cargo.toml").exists():
        return "cargo clippy -q -- -D warnings"
    if (root / "package.json").exists():
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            lint_script = str((data.get("scripts") or {}).get("lint") or "").strip()
        except (OSError, ValueError):
            lint_script = ""
        # Prefer the project's own lint script; it knows which tool it uses.
        if lint_script:
            return "npm run lint --silent"
        # --no-install fails hard when eslint is not already in node_modules,
        # so only offer it when the local binary actually exists.
        if shutil.which("npx") and _has_local_npm_bin(root, "eslint"):
            return "npx --no-install eslint ."
    if shutil.which("ruff"):
        return "ruff check ."
    if shutil.which("flake8"):
        return "flake8 ."
    if shutil.which("pyflakes"):
        return "pyflakes ."
    return None


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def find_files(name: str, cwd: Optional[Path] = None, limit: int = 50) -> Tuple[int, str]:
    root = Path(cwd or Path.cwd())
    pattern = (name or "").strip()
    if not pattern:
        return 0, ""
    hits: List[str] = []
    total = 0
    for path in _iter_files(root):
        if pattern.lower() in path.name.lower():
            total += 1
            if len(hits) < limit:
                hits.append(str(path.relative_to(root)))
    return total, "\n".join(hits)


def grep_repo(pattern: str, cwd: Optional[Path] = None, max_lines: int = 80) -> Tuple[int, str]:
    """Search the working tree, preferring ripgrep, then git grep, then grep."""
    root = Path(cwd or Path.cwd())
    needle = (pattern or "").strip()
    if not needle:
        return 0, ""

    quoted = json.dumps(needle)
    if shutil.which("rg"):
        code, out = run_shell_capture(
            f"rg -n --no-heading --color never --max-count 200 -e {quoted} .",
            cwd=root, timeout=120,
        )
    elif shutil.which("grep"):
        # Plain grep, not `git grep`: untracked-but-ignored dirs aside, git grep
        # silently misses new files that were never added.
        code, out = run_shell_capture(
            "grep -rnI --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv "
            f"--exclude-dir=node_modules --exclude-dir=__pycache__ -e {quoted} .",
            cwd=root, timeout=120,
        )
    else:
        code, out = run_shell_capture(
            f"git grep -n --no-color -e {quoted}", cwd=root, timeout=120
        )
    if code not in (0, 1) or not out.strip():
        return 0, out.strip()
    lines = out.splitlines()
    return len(lines), "\n".join(lines[:max_lines])


def git_stash(action: str, label: str = "", cwd: Optional[Path] = None) -> Tuple[bool, str]:
    root = Path(cwd or Path.cwd())
    if not (root / ".git").exists():
        return False, "Bukan git repository."
    act = (action or "push").lower()
    msg = (label or "").strip()
    if act in ("push", "save"):
        if not msg:
            msg = "onno-x snapshot"
        code, out = run_shell_capture(f'git stash push -m {json.dumps(msg)}', cwd=root, timeout=120)
    elif act in ("pop", "apply"):
        code, out = run_shell_capture(f"git stash {act}", cwd=root, timeout=120)
    elif act in ("drop", "clear"):
        code, out = run_shell_capture(f"git stash {act}", cwd=root, timeout=120)
    else:
        code, out = run_shell_capture("git stash list", cwd=root, timeout=60)
    return code == 0, out.strip() or "(no output)"


def git_log(count: int = 10, cwd: Optional[Path] = None) -> Tuple[bool, str]:
    root = Path(cwd or Path.cwd())
    if not (root / ".git").exists():
        return False, "Bukan git repository."
    n = max(1, min(int(count or 10), 100))
    code, out = run_shell_capture(
        f"git log -n {n} --date=short --pretty=format:'%h %ad %s (%an)' --stat",
        cwd=root, timeout=60,
    )
    return code == 0, out.strip() or "(belum ada commit)"


def find_command_help(command_table: List[Tuple[str, str]], arg: str) -> Optional[str]:
    """Text for ``/help <command>``: exact match first, then substring matches.

    Returns None when nothing matches, so the caller can fall back to the menu.
    """
    needle = (arg or "").strip().lower().lstrip("/")
    if not needle:
        return None
    needle = "/" + needle

    hits = [(c, d) for c, d in command_table if c.lower() == needle]
    if not hits:
        hits = [(c, d) for c, d in command_table if needle in c.lower()]
    if not hits:
        return None

    lines = []
    for cmd, desc in hits[:5]:
        lines.append(f"**{cmd}** \u2014 {desc}")
    if len(hits) > 5:
        lines.append(f"_...dan {len(hits) - 5} command lain yang mengandung '{needle}'._")

    name = hits[0][0].lower()
    aliases = [
        c for c, d in command_table
        if d.lower().startswith("alias") and name in d.lower()
    ]
    if aliases:
        lines.append("Alias: " + ", ".join(f"`{a}`" for a in aliases[:8]))
    return "\n\n".join(lines)


def token_breakdown(messages: List[Dict[str, Any]]) -> List[Tuple[str, int, int]]:
    """(category, messages, tokens) rows, biggest first."""
    buckets: Dict[str, List[int]] = {}
    for m in messages:
        role = m.get("role", "unknown")
        if role == "tool":
            key = "tool result"
        elif role == "assistant" and m.get("tool_calls"):
            key = "tool call args"
        elif role == "assistant":
            key = "assistant reply"
        elif role == "system":
            key = "system prompt"
        else:
            key = "user input"
        entry = buckets.setdefault(key, [0, 0])
        entry[0] += 1
        entry[1] += estimate_tokens([m])
    rows = [(k, v[0], v[1]) for k, v in buckets.items()]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows
