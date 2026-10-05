"""Service defaults and safe YAML configuration loading."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS: dict[str, Any] = {
    "port": 47625,
    "token_file": str(Path.home() / "Library/Application Support/super-input/token"),
    "model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "trust": "T0",
    "min_syllables": 2,
    "l1_conf_threshold": 0.5,
    "timeout_ms": 1500,
    "context_window": 200,
    "debounce_ms": 500,
    "warmup": False,
    "cloud": {"enabled": False, "base_url": "", "model": ""},
    "schema": str(REPO_ROOT / "assets/superpinyin.schema.yaml"),
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load defaults and merge the optional user YAML file.

    ``path=None`` reads ``~/.superinput/rerank.yaml`` if present. Unknown keys
    are retained for forward compatibility; the nested cloud mapping is merged
    rather than replaced.
    """
    config = copy.deepcopy(DEFAULTS)
    config_path = Path(path).expanduser() if path is not None else Path.home() / ".superinput/rerank.yaml"
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ValueError("configuration root must be a YAML mapping")
        cloud = loaded.get("cloud", {})
        if cloud is not None and not isinstance(cloud, dict):
            raise ValueError("cloud configuration must be a mapping")
        for key, value in loaded.items():
            if key == "cloud":
                config["cloud"].update(cloud or {})
            else:
                config[key] = value
    schema = Path(config["schema"]).expanduser()
    if not schema.is_absolute():
        schema = (config_path.parent / schema).resolve() if path is not None else (REPO_ROOT / schema).resolve()
    config["schema"] = str(schema)
    return config
