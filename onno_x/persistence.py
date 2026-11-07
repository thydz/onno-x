import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def save_session(
    session_id: str,
    messages: List[Dict[str, Any]],
    model_name: str,
    turns_count: int,
    permission_mode: str = "auto",
    plan_mode: bool = False,
    project_dir: Optional[str] = None,
) -> Path:
    """Save session state to disk."""
    sdir = get_sessions_dir(project_dir)
    file_path = sdir / f"{session_id}.json"

    data = {
        "session_id": session_id,
        "updated_at": datetime.now().isoformat(),
        "model_name": model_name,
        "turns_count": turns_count,
        "permission_mode": permission_mode,
        "plan_mode": plan_mode,
        "cwd": str(Path.cwd().resolve()),
        "messages": messages,
    }

    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return file_path


def load_session(session_id: str, project_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load session by id."""
    sdir = get_sessions_dir(project_dir)
    target = sdir / f"{session_id}.json"
    if not target.exists():
        # Check home dir fallback
        home_target = Path.home() / ".onno-x" / "sessions" / f"{session_id}.json"
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
            sessions.append({
                "id": sid,
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


def get_latest_session(project_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the most recently updated session."""
    sessions = list_sessions(project_dir)
    if not sessions:
        return None
    return load_session(sessions[0]["id"], project_dir)


def delete_session(session_id: str, project_dir: Optional[str] = None) -> bool:
    """Delete a saved session."""
    sdir = get_sessions_dir(project_dir)
    target = sdir / f"{session_id}.json"
    if target.exists():
        try:
            target.unlink()
            return True
        except Exception:
            pass
    return False

