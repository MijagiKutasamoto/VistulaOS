import json
import os
from dataclasses import dataclass
from typing import Any, Optional


def _project_root() -> str:
    # src/i18n.py -> project root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _detect_lang() -> str:
    # Highest priority: explicit override
    override = os.environ.get("VISTULA_LANG")
    if override:
        return override

    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return value

    return "en"


def _normalize_lang(lang: str) -> str:
    # Examples: pl_PL.UTF-8 -> pl, en_US -> en
    lang = (lang or "").strip()
    if not lang:
        return "en"

    if "." in lang:
        lang = lang.split(".", 1)[0]
    if "@" in lang:
        lang = lang.split("@", 1)[0]
    if "_" in lang:
        lang = lang.split("_", 1)[0]

    lang = lang.lower()
    if lang in ("pl", "en"):
        return lang
    return "en"


@dataclass(frozen=True)
class Translator:
    lang: str
    messages: dict[str, str]

    @classmethod
    def load(cls) -> "Translator":
        lang = _normalize_lang(_detect_lang())
        root = _project_root()
        path = os.path.join(root, "data", "i18n", f"{lang}.json")

        messages: dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw: Any = json.load(f)
            if isinstance(raw, dict):
                messages = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            messages = {}

        return cls(lang=lang, messages=messages)

    def t(self, key: str, default: Optional[str] = None) -> str:
        if key in self.messages:
            return self.messages[key]
        return default if default is not None else key
