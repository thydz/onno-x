import json
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


class Config(BaseModel):
    active_model: str = "onno-ai"
    max_steps: int = 50
    auto_resume: bool = False
    models: Dict[str, ModelSpec] = Field(default_factory=dict)


DEFAULT_MODELS: Dict[str, ModelSpec] = {
    "onno-ai": ModelSpec(
        name="onno-ai",
        provider="openai",
        model_id="onno-ai",
        base_url="http://192.168.100.105:8084",
        api_key="ollama",
    ),
    "claude-sonnet": ModelSpec(
        name="claude-sonnet",
        provider="anthropic",
        model_id="claude-3-5-sonnet-20241022",
        api_key=None,
    ),
    "gpt-4o": ModelSpec(
        name="gpt-4o",
        provider="openai",
        model_id="gpt-4o",
        api_key=None,
        base_url="https://api.openai.com/v1",
    ),
    "llama3": ModelSpec(
        name="llama3",
        provider="ollama",
        model_id="llama3.1:latest",
        base_url="http://localhost:11434",
    ),
    "qwen-coder": ModelSpec(
        name="qwen-coder",
        provider="openai",
        model_id="qwen2.5-coder:7b",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
}


def load_config() -> Config:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        cfg = Config(active_model="onno-ai", models=DEFAULT_MODELS)
        save_config(cfg)
        return cfg

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return Config(**data)
    except Exception:
        cfg = Config(active_model="onno-ai", models=DEFAULT_MODELS)
        return cfg


def save_config(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
