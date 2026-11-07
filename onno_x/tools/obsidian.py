import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx

OBSIDIAN_HOST = "192.168.100.102"
OBSIDIAN_HTTP_PORT = 2233
OBSIDIAN_REMOTE_PATH = "/home/kali/Obsidian/Onnobot_Memory"


def obsidian_search_notes(query: str, limit: int = 10) -> str:
    """Search knowledge notes, reports, and bug bounty findings in Obsidian memory."""
    try:
        # Use fast remote grep over SSH
        safe_q = query.replace("'", "").replace('"', "")
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=3",
            f"kali@{OBSIDIAN_HOST}",
            f"grep -rni --max-count=2 '{safe_q}' {OBSIDIAN_REMOTE_PATH} | head -n {limit * 3}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        output = res.stdout.strip()
        if not output:
            return f"No Obsidian memory notes found matching query: '{query}'"

        lines = output.splitlines()
        results = []
        for line in lines[:limit]:
            clean_line = line.replace(OBSIDIAN_REMOTE_PATH + "/", "")
            results.append(clean_line)

        return f"Found Obsidian memory notes matching '{query}':\n" + "\n".join(results)
    except Exception as e:
        return f"Error searching Obsidian memory: {str(e)}"


def obsidian_read_note(note_name: str) -> str:
    """Read the full markdown content of a note from Obsidian memory."""
    clean_name = note_name.strip().lstrip("/")
    if not clean_name.endswith(".md"):
        clean_name += ".md"

    # Try HTTP first
    url = f"http://{OBSIDIAN_HOST}:{OBSIDIAN_HTTP_PORT}/Onnobot_Memory/{clean_name}"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.text
    except Exception:
        pass

    # Fallback to SSH read
    try:
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=3",
            f"kali@{OBSIDIAN_HOST}",
            f"cat '{OBSIDIAN_REMOTE_PATH}/{clean_name}' 2>/dev/null || cat '{OBSIDIAN_REMOTE_PATH}/Knowledge/{clean_name}' 2>/dev/null",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        return f"Note '{clean_name}' not found in Obsidian memory."
    except Exception as e:
        return f"Error reading note: {str(e)}"


def obsidian_write_note(title: str, content: str, folder: str = "Knowledge") -> str:
    """Save or update a note in Obsidian memory (Knowledge, Tasks, or root)."""
    clean_title = title.strip().replace(" ", "_").replace("/", "_")
    if not clean_title.endswith(".md"):
        clean_title += ".md"

    target_dir = f"{OBSIDIAN_REMOTE_PATH}/{folder}" if folder else OBSIDIAN_REMOTE_PATH
    target_path = f"{target_dir}/{clean_title}"

    today = datetime.now().strftime("%Y-%m-%d")
    header = f"---\ntitle: \"{title}\"\ndate: {today}\ntags: [onno-x, cyber, auto-memory]\n---\n\n"
    full_content = header + content

    try:
        # Transfer content safely via SSH stdin
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            f"kali@{OBSIDIAN_HOST}",
            f"mkdir -p '{target_dir}' && cat > '{target_path}'",
        ]
        proc = subprocess.run(cmd, input=full_content, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return f"Successfully saved memory note to Obsidian: {folder}/{clean_title}"
        return f"Failed to save note: {proc.stderr}"
    except Exception as e:
        return f"Error writing to Obsidian: {str(e)}"

