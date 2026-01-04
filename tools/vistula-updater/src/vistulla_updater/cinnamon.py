from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio


@dataclass(frozen=True)
class CinnamonTheme:
    gtk_theme: Optional[str]
    icon_theme: Optional[str]


def read_cinnamon_theme() -> CinnamonTheme:
    # Cinnamon stores interface settings in org.cinnamon.desktop.interface
    settings = Gio.Settings.new("org.cinnamon.desktop.interface")
    gtk_theme = settings.get_string("gtk-theme") if settings.contains("gtk-theme") else None
    icon_theme = settings.get_string("icon-theme") if settings.contains("icon-theme") else None
    gtk_theme = gtk_theme or None
    icon_theme = icon_theme or None
    return CinnamonTheme(gtk_theme=gtk_theme, icon_theme=icon_theme)
