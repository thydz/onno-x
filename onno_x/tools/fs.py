import itertools
import re
import shutil
from pathlib import Path
from typing import Tuple
from onno_x.hooks import run_post_edit_hook
from onno_x.ui import print_file_diff

_ACTIVE_SESSION = None

BINARY_EXTENSIONS = {
    ".gguf", ".bin", ".iso", ".dmg", ".exe", ".dylib", ".so", ".a", ".o",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".db", ".sqlite",
    ".sqlite3", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".mp3", ".mp4", ".mov", ".mkv", ".wav", ".pyc", ".wasm", ".whl", ".parquet",
}


def set_active_session_for_fs(session):
    global _ACTIVE_SESSION
    _ACTIVE_SESSION = session


def is_binary_or_oversized(p: Path, max_bytes: int = 2_000_000) -> Tuple[bool, str]:
    """Check if file is too large or binary to prevent memory explosion and freezing."""
    try:
        st = p.stat()
        if st.st_size > max_bytes:
            return True, f"File is too large ({st.st_size / (1024*1024):.1f} MB > limit {max_bytes / (1024*1024):.1f} MB)"
        if p.suffix.lower() in BINARY_EXTENSIONS:
            return True, f"Binary file format ({p.suffix})"
        # Check initial sample for null bytes (typical in binary files)
        with open(p, "rb") as f:
            chunk = f.read(1024)
            if b"\0" in chunk:
                return True, "Binary file detected"
    except Exception as e:
        return True, str(e)
    return False, ""


def record_file_snapshot(p: Path):
    """Record original file content into current session checkpoint before modification."""
    if _ACTIVE_SESSION and _ACTIVE_SESSION.checkpoints:
        active_cp = _ACTIVE_SESSION.checkpoints[-1]
        snapshots = active_cp.setdefault("file_snapshots", {})
        key = str(p.resolve())
        if key not in snapshots:
            if p.exists() and p.is_file():
                try:
                    # Do not snapshot huge files into memory
                    if p.stat().st_size <= 2_000_000:
                        snapshots[key] = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            elif not p.exists():
                snapshots[key] = None  # None = newly created file


def read_file(path: str, offset: int = 1, max_lines: int = 150) -> str:
    """Read contents of file starting from offset up to max_lines using streaming."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: File not found: {path}"
    if p.is_dir():
        return f"Error: {path} is a directory."

    bad, reason = is_binary_or_oversized(p, max_bytes=5_000_000)
    if bad:
        return f"Error: Cannot read {path} - {reason}."

    try:
        # Stream read line by line rather than reading whole multi-GB file into RAM
        lines = []
        start = max(1, offset)
        limit = min(max_lines, 300)
        end = start + limit
        total_seen = 0

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                total_seen = i
                if i >= start and i < end:
                    lines.append(f"{i}\t{line.rstrip(chr(10)).rstrip(chr(13))}")
                elif i >= end:
                    break

        if offset > total_seen and total_seen > 0:
            return f"(offset {offset} exceeds total line count of {total_seen})"

        content = "\n".join(lines)
        if total_seen >= end:
            content += f"\n... (more lines remaining. Read further with offset={end})"
        return content or "(empty file)"
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(path: str, content: str) -> str:
    """Create new file or overwrite entire file with content."""
    p = Path(path).resolve()
    record_file_snapshot(p)
    try:
        old_content = p.read_text(encoding="utf-8") if p.exists() else ""
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if old_content:
            print_file_diff(str(p.name), old_content, content)
        hook_feedback = run_post_edit_hook(str(p))
        res_msg = f"Successfully wrote {len(content)} characters to {path}"
        if hook_feedback:
            res_msg += f"\n{hook_feedback}"
        return res_msg
    except Exception as e:
        return f"Error writing file: {str(e)}"


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replace exact text occurrences in a file (like Claude Code Edit tool)."""
    p = Path(path).resolve()
    record_file_snapshot(p)
    if not p.exists():
        return f"Error: File not found: {path}"
    if p.is_dir():
        return f"Error: {path} is a directory."

    try:
        content = p.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {path}"
        if count > 1 and not replace_all:
            return f"Error: old_string occurs {count} times in {path}. Provide more context or set replace_all=true."

        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        p.write_text(new_content, encoding="utf-8")
        print_file_diff(str(p.name), content, new_content)
        hook_feedback = run_post_edit_hook(str(p))
        res_msg = f"Successfully replaced {count if replace_all else 1} occurrence(s) in {path}"
        if hook_feedback:
            res_msg += f"\n{hook_feedback}"
        return res_msg
    except Exception as e:
        return f"Error editing file: {str(e)}"


def delete_file(path: str) -> str:
    """Delete a file or directory."""
    p = Path(path).resolve()
    record_file_snapshot(p)
    if not p.exists():
        return f"Error: Path not found: {path}"

    try:
        if p.is_dir():
            shutil.rmtree(p)
            return f"Successfully deleted directory: {path}"
        else:
            p.unlink()
            return f"Successfully deleted file: {path}"
    except Exception as e:
        return f"Error deleting {path}: {str(e)}"


def list_dir(path: str = ".") -> str:
    """List directory entries."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: Path not found: {path}"
    if not p.is_dir():
        return f"Error: {path} is not a directory."

    try:
        entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        lines = []
        for e in entries:
            prefix = "[DIR] " if e.is_dir() else "[FILE]"
            lines.append(f"{prefix} {e.name}")
        return "\n".join(lines) or "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def grep_search(pattern: str, path: str = ".", file_pattern: str = "*") -> str:
    """Search for regex pattern across files in directory safely without reading huge binaries."""
    root = Path(path).resolve()
    if not root.exists():
        return f"Error: Path not found: {path}"

    results = []
    ignored_dir_names = {
        ".git", ".venv", "venv", "node_modules", "__pycache__", ".onno-x",
        ".gemini", "dist", "build", "Library", "Downloads", "Movies", "Music", "Pictures"
    }

    try:
        regex = re.compile(pattern, re.IGNORECASE)
        for p in root.rglob(file_pattern):
            # Skip common non-code / bloated directories
            if any(part in ignored_dir_names or part.startswith(".") for part in p.parts):
                continue

            if p.is_file():
                bad, _ = is_binary_or_oversized(p, max_bytes=1_000_000)
                if bad:
                    continue

                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = p.relative_to(root)
                                results.append(f"{rel_path}:{idx}: {line.strip()[:150]}")
                                if len(results) >= 50:
                                    break
                except Exception:
                    continue

            if len(results) >= 50:
                results.append("... (more matches truncated at 50 results)")
                break

        return "\n".join(results) or f"No matches found for pattern '{pattern}'"
    except Exception as e:
        return f"Error in grep_search: {str(e)}"
