from __future__ import annotations

from pathlib import Path


def _theme_dirs() -> list[Path]:
    return [
        Path.home() / ".themes",
        Path("/usr/share/themes"),
        Path("/usr/local/share/themes"),
    ]


def list_gtk_themes() -> list[str]:
    themes: set[str] = set()
    for d in _theme_dirs():
        if not d.exists() or not d.is_dir():
            continue
        for child in d.iterdir():
            if not child.is_dir():
                continue
            # Typical GTK themes ship with gtk-3.0 folder.
            if (child / "gtk-3.0").exists() or (child / "gtk-4.0").exists():
                themes.add(child.name)
    return sorted(themes, key=str.casefold)
