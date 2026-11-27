import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".onno-x"
CONFIG_FILE = CONFIG_DIR / "config.json"


class ModelSpec(BaseModel):
    name: str
    provider: str  # "openai", "anthropic", "ollama"
    model_id: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 300.0
    # USD per 1M tokens, as published by the provider. 0.0 = unknown/local, and
    # /cost then reports the token counts without inventing a price.
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0


class Config(BaseModel):
    active_model: str = ""
    max_steps: int = 50
    auto_resume: bool = False
    # Accent colour for the prompt box, toolbar and banner (/color).
    accent_color: str = "cyan"
    # Token threshold for auto-compaction. None = derive from model capacity;
    # 0 disables auto-compaction entirely (/autocompact).
    autocompact_threshold: Optional[int] = None
    # External memory/tooling endpoint. Empty = disabled; override per install
    # or via ONNO_OBSIDIAN_URL. No hardcoded host/IP shipped.
    obsidian_url: str = ""
    # Terminal bell when a turn runs longer than 8s (/notify).
    notify_completion: bool = True
    # Run the project's test/lint command after a turn that edited files
    # (/autoverify). Detection is best-effort; nothing runs when none is found.
    auto_verify: bool = True
    # User-defined slash aliases: name -> command template (/alias).
    aliases: Dict[str, str] = Field(default_factory=dict)
    models: Dict[str, ModelSpec] = Field(default_factory=dict)


def obsidian_url() -> str:
    """Obsidian memory endpoint: env var wins so CI/other hosts need no config edit.

    Empty string means no hardcoded host/IP; Obsidian tools simply find nothing.
    """
    env = os.environ.get("ONNO_OBSIDIAN_URL")
    if env:
        return env.rstrip("/")
    try:
        return (load_config().obsidian_url or "").rstrip("/")
    except Exception:
        return ""


# No shipped model registry: no model_id, no base_url, no api_key, no private
# IP. Add your own with `onno-x model add` / edit ~/.onno-x/config.json.
DEFAULT_MODELS: Dict[str, ModelSpec] = {}


def _quarantine_config(exc: Exception) -> None:
    """Move an unreadable config aside instead of overwriting it on the next save."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup: Optional[Path] = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.corrupt-{stamp}")
    try:
        CONFIG_FILE.replace(backup)
    except OSError:
        backup = None

    moved = f" File lama dipindahkan ke {backup}." if backup else ""
    print(
        f"[onno-x] Config tidak bisa dibaca ({exc})."
        f"{moved} Memakai model default untuk sesi ini.",
        file=sys.stderr,
    )


def load_config() -> Config:
    """Load the config, never silently discarding a damaged one.

    A broken config.json used to be replaced by DEFAULT_MODELS in memory, so the
    next save_config (a /model switch, a /steps change) wrote defaults over the
    user's file and destroyed their API keys. Now the bad file is renamed to
    config.json.corrupt-<timestamp> and the fallback is reported on stderr.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        cfg = Config(active_model="", models=dict(DEFAULT_MODELS))
        save_config(cfg)
        return cfg

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"expected a JSON object, got {type(data).__name__}")
        cfg = Config(**data)
    except Exception as exc:
        _quarantine_config(exc)
        return Config(active_model="", models=dict(DEFAULT_MODELS))

    # An empty model table or a dangling active_model leaves the CLI unusable.
    if not cfg.models:
        cfg.models = dict(DEFAULT_MODELS)
    if cfg.active_model not in cfg.models:
        cfg.active_model = next(iter(cfg.models), "")
    return cfg


def save_config(cfg: Config) -> None:
    """Write the config atomically so a crash can't truncate it.

    The temp file is created with mkstemp (mode 0600) because the file holds API
    keys, then renamed over CONFIG_FILE with os.replace.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump_json(indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, CONFIG_FILE)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
