from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class AppConfig:
    language: str = "pl"
    store_remote: str = ""
    categories: dict[str, list[str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.categories is None:
            self.categories = {}


def _config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        base = Path(xdg_config_home)
    else:
        base = Path.home() / ".config"
    return base / "vistulla-updater" / "config.json"


def load_config() -> AppConfig:
    path = _config_path()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        return AppConfig()
    except Exception:
        return AppConfig()

    language = str(data.get("language", "pl"))
    if language not in ("pl", "en"):
        language = "pl"
    store_remote = str(data.get("store_remote", "") or "")
    # Basic sanitization: remote names are simple identifiers; also avoid "$" which is our log prefix.
    if store_remote == "$" or (store_remote and any(ch.isspace() for ch in store_remote)):
        store_remote = ""

    raw_categories = data.get("categories", {})
    categories: dict[str, list[str]] = {}
    if isinstance(raw_categories, dict):
        for k, v in raw_categories.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, list):
                categories[k] = [str(x) for x in v if str(x).strip()]
    return AppConfig(language=language, store_remote=store_remote, categories=categories)


def save_config(cfg: AppConfig) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {
        "language": cfg.language,
        "store_remote": cfg.store_remote,
        "categories": cfg.categories,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
