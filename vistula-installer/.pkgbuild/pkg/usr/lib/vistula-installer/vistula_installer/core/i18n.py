from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass
class I18n:
    language: str
    translations: Mapping[str, str]

    def t(self, msgid: str) -> str:
        return self.translations.get(msgid, msgid)


def load_i18n(language: str) -> I18n:
    # Resolve assets directory:
    # - dev mode: repo root-ish next to package
    # - PyInstaller: sys._MEIPASS
    # - override: VISTULA_INSTALLER_ASSETS
    override = os.environ.get("VISTULA_INSTALLER_ASSETS")
    if override:
        assets_root = Path(override)
    else:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            assets_root = Path(str(meipass))
        else:
            assets_root = Path(__file__).resolve().parents[2]  # repo root-ish

    assets = assets_root / "assets" / "i18n"
    path = assets / f"{language}.json"

    translations: dict[str, str] = {}
    if path.exists():
        try:
            translations = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            translations = {}
    return I18n(language=language, translations=translations)
