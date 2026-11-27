import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from onno_x.config import CONFIG_DIR


def get_sessions_dir(project_dir: Optional[str] = None) -> Path:
    """Get project-local or global sessions directory."""
    if project_dir:
        p = Path(project_dir) / ".onno-x" / "sessions"
    else:
        # Check current working directory first, fallback to home directory
        local = Path.cwd() / ".onno-x" / "sessions"
        if local.parent.exists():
            p = local
        else:
            p = Path.home() / ".onno-x" / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_session_id(session_id: str) -> Optional[str]:
    """Return a safe session id, or None if it could escape the sessions dir.

    Session ids are used as filenames (`<id>.json`), and load_session() accepts
    ids from the CLI (`/resume`) and from the web API. Without this guard a
    value like `../../other` reads arbitrary *.json files on disk.
    """
    if not isinstance(session_id, str):
        return None
    sid = session_id.strip()
    if not sid or sid.startswith("."):
        return None
    if "/" in sid or "\\" in sid or "\x00" in sid:
        return None
    if Path(sid).name != sid:
        return None
    return sid


def save_session(
    session_id: str,
    messages: List[Dict[str, Any]],
    model_name: str,
    turns_count: int,
    permission_mode: str = "auto",
    plan_mode: bool = False,
    project_dir: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Path:
    """Save session state to disk.

    `state` carries extra UI/session fields (extra_dirs, output_style, goal, ...)
    so /resume restores more than the transcript.
    """
    sid = sanitize_session_id(session_id)
    if not sid:
        raise ValueError(f"Invalid session id: {session_id!r}")
    sdir = get_sessions_dir(project_dir)
    file_path = sdir / f"{sid}.json"

    data = {
        # Store the sanitized id: the file is named with it, and a raw id made
        # load_session() report a different id than the filename.
        "session_id": sid,
        "updated_at": datetime.now().isoformat(),
        "model_name": model_name,
        "turns_count": turns_count,
        "permission_mode": permission_mode,
        "plan_mode": plan_mode,
        "cwd": str(Path.cwd().resolve()),
        "messages": messages,
    }
    if state:
        data.update(state)

    write_json_atomic(file_path, data)
    return file_path


def write_json_atomic(path: Path, data: Dict[str, Any], mode: int = 0o600) -> None:
    """Write JSON through a temp file + rename so a crash never truncates it.

    Sessions are rewritten as often as every turn; a plain write_text() that is
    interrupted leaves a half-written .json that load_session() silently refuses.
    The temp file lives in the same directory so os.replace() stays atomic.
    """
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def load_session(session_id: str, project_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load session by id."""
    sid = sanitize_session_id(session_id)
    if not sid:
        return None
    sdir = get_sessions_dir(project_dir)
    target = sdir / f"{sid}.json"
    if not target.exists():
        # Check home dir fallback
        home_target = Path.home() / ".onno-x" / "sessions" / f"{sid}.json"
        if home_target.exists():
            target = home_target
        else:
            return None

    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_sessions(project_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all saved sessions sorted by most recent."""
    sdir = get_sessions_dir(project_dir)
    sessions = []
    seen_ids = set()

    for p in list(sdir.glob("*.json")) + list((Path.home() / ".onno-x" / "sessions").glob("*.json")):
        sid = p.stem
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            msg_count = len(data.get("messages", []))
            # /title wins over the auto-derived first user message.
            title = data.get("title") or next(
                (m.get("content", "") for m in data.get("messages", [])
                 if m.get("role") == "user" and isinstance(m.get("content"), str)),
                "",
            )
            sessions.append({
                "id": sid,
                "title": " ".join(title.split())[:60] or sid,
                "updated_at": data.get("updated_at", ""),
                "model_name": data.get("model_name", "unknown"),
                "turns_count": data.get("turns_count", 0),
                "messages_count": msg_count,
                "cwd": data.get("cwd", ""),
                "path": str(p),
            })
        except Exception:
            continue

    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions


DRAFT_FILE = CONFIG_DIR / "draft.json"


def save_draft(text: str, cwd: Optional[str] = None) -> bool:
    """Keep one unfinished prompt so a crash or Ctrl+C does not eat it."""
    body = (text or "").strip()
    if not body:
        return False
    payload = {
        "text": body,
        "cwd": cwd or os.getcwd(),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        DRAFT_FILE.parent.mkdir(parents=True, exist_ok=True)
        DRAFT_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def load_draft(cwd: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Return the stored draft for this working directory, if any."""
    try:
        data = json.loads(DRAFT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    text = str(data.get("text") or "").strip()
    if not text:
        return None
    if (data.get("cwd") or "") != (cwd or os.getcwd()):
        # Belongs to another project; leave it there instead of pasting it here.
        return None
    return {
        "text": text,
        "cwd": str(data.get("cwd") or ""),
        "saved_at": str(data.get("saved_at") or ""),
    }


def clear_draft() -> bool:
    try:
        DRAFT_FILE.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def search_sessions(query: str, project_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filter saved sessions by a case-insensitive substring of id/title/model/workspace."""
    needle = " ".join((query or "").lower().split())
    if not needle:
        return list_sessions(project_dir)
    out = []
    for s in list_sessions(project_dir):
        haystack = " ".join(
            str(s.get(k) or "") for k in ("id", "title", "model_name", "cwd")
        ).lower()
        if needle in haystack:
            out.append(s)
    return out


def resolve_session_ref(ref: str, project_dir: Optional[str] = None) -> Optional[str]:
    """Turn what the user typed into a session id.

    Accepts a numbered row from /sessions (``3``), a full id, or a unique id
    prefix, so nobody has to copy 40 hex characters. Returns None when nothing
    matches or a prefix is ambiguous.
    """
    target = (ref or "").strip()
    if not target:
        return None

    sessions = list_sessions(project_dir)
    if target.isdecimal():
        idx = int(target)
        if 1 <= idx <= len(sessions):
            return sessions[idx - 1]["id"]
        return None

    for s in sessions:
        if s["id"] == target:
            return target
    matches = [s["id"] for s in sessions if s["id"].startswith(target)]
    if len(matches) == 1:
        return matches[0]
    return None


def get_latest_session(project_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the most recently updated session."""
    sessions = list_sessions(project_dir)
    if not sessions:
        return None
    return load_session(sessions[0]["id"], project_dir)


def delete_session(session_id: str, project_dir: Optional[str] = None) -> bool:
    """Delete a saved session (local + home fallback, same dirs as list_sessions)."""
    # Tolak path traversal: id harus nama file polos.
    sid = sanitize_session_id(session_id)
    if not sid:
        return False
    deleted = False
    for d in {get_sessions_dir(project_dir), Path.home() / ".onno-x" / "sessions"}:
        target = d / f"{sid}.json"
        if target.exists():
            try:
                target.unlink()
                deleted = True
            except Exception:
                pass
    return deleted

