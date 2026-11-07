import subprocess
from pathlib import Path


def run_shell(command: str, timeout: int = 60) -> str:
    """Run bash command in current working directory."""
    try:
        res = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.cwd()),
            start_new_session=True,
        )
        out = res.stdout
        if res.stderr:
            out += f"\n[stderr]\n{res.stderr}"
        if res.returncode != 0:
            out += f"\n[exit code: {res.returncode}]"
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing shell: {str(e)}"
