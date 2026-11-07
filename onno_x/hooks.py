import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def find_hook_script(hook_name: str) -> Optional[Path]:
    """Find hook script in workspace .onno-x/hooks/ or ~/.onno-x/hooks/."""
    candidates = [
        Path.cwd() / ".onno-x" / "hooks" / hook_name,
        Path.cwd() / ".onno-x" / "hooks" / f"{hook_name}.sh",
        Path.home() / ".onno-x" / "hooks" / hook_name,
        Path.home() / ".onno-x" / "hooks" / f"{hook_name}.sh",
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return c
        elif c.exists() and c.is_file():
            # If exists but not chmod +x, still run with bash
            return c
    return None


def run_post_edit_hook(file_path: str) -> Optional[str]:
    """Run post-edit hook (e.g. linter, formatter, type checker) after a file is modified."""
    hook = find_hook_script("post-edit")
    if not hook:
        return None

    try:
        cmd = [str(hook), file_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = (res.stdout + "\n" + res.stderr).strip()
        if res.returncode != 0:
            return f"[Hook post-edit Warning/Error (code {res.returncode})]:\n{output}"
        return output if output else None
    except Exception as e:
        return f"[Hook post-edit execution failed]: {str(e)}"

