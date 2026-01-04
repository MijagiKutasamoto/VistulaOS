#!/usr/bin/env python3
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

from i18n import Translator

__version__ = "1.0.0"

# Pozwól sprawdzić wersję bez ładowania GTK/VTE (np. w środowisku bez GI).
if __name__ == "__main__" and "--version" in sys.argv[1:]:
    print(__version__)
    raise SystemExit(0)

try:
    import gi

    require_version = getattr(gi, "require_version", None)
    if require_version is None:
        raise ImportError("PyGObject (python3-gi) nie jest zainstalowany")

    # Ważne: ustaw wersje *zanim* zaimportujemy cokolwiek z gi.repository,
    # żeby nie wczytał się przypadkiem Gdk 4.x.
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gio", "2.0")
    gi.require_version("GLib", "2.0")
    gi.require_version("Pango", "1.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("Vte", "2.91")

    from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402
except Exception as exc:  # pragma: no cover
    tr = Translator.load()
    print(tr.t("error.missing_deps.title", "Błąd: brak zależności do uruchomienia GUI terminala."))
    print(tr.t("error.missing_deps.hint", "Zainstaluj: python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91"))
    print(f"Szczegóły: {exc}")
    raise SystemExit(1)


PASSWORD_PROMPT_RE = re.compile(
    r"(?:\bpassword\b|\bpassphrase\b|\bhas\u0142o\b|\bpin\b)[^\n]*[:\uFF1A>]\s*$",
    re.IGNORECASE,
)


@dataclass
class PasswordMode:
    active: bool = False
    last_trigger_row: Optional[int] = None


class VistulaTerminalWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, command_argv: Optional[list[str]] = None):
        super().__init__(application=app)
        self._tr = Translator.load()
        self.set_title(self._tr.t("app.title", "Vistula Terminal"))
        self.set_default_size(860, 520)

        self._password = PasswordMode()

        self._overlay = Gtk.Overlay()
        self.add(self._overlay)

        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(10000)
        self.terminal.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self._overlay.add(self.terminal)

        # Password entry overlay (bottom)
        self._password_revealer = Gtk.Revealer()
        self._password_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self._password_revealer.set_transition_duration(100)
        self._password_revealer.set_halign(Gtk.Align.FILL)
        self._password_revealer.set_valign(Gtk.Align.END)

        self._password_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._password_box.set_margin_start(8)
        self._password_box.set_margin_end(8)
        self._password_box.set_margin_bottom(8)

        self._password_label = Gtk.Label(label="Hasło:")
        self._password_label.set_label(self._tr.t("password.label", "Hasło:"))
        self._password_label.set_halign(Gtk.Align.START)
        self._password_label.set_valign(Gtk.Align.CENTER)
        self._password_label.set_margin_end(8)

        self._password_entry = Gtk.Entry()
        self._password_entry.set_hexpand(True)
        self._password_entry.set_visibility(False)
        self._password_entry.set_invisible_char("*")
        self._password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self._password_entry.set_activates_default(False)

        self._password_box.pack_start(self._password_label, False, False, 0)
        self._password_box.pack_start(self._password_entry, True, True, 0)
        self._password_revealer.add(self._password_box)
        self._overlay.add_overlay(self._password_revealer)

        self._apply_font_from_cinnamon_settings()
        self._apply_icon()

        # Copy/paste shortcuts
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        accel.connect(Gdk.keyval_from_name("C"), Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0, self._on_copy)
        accel.connect(Gdk.keyval_from_name("V"), Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0, self._on_paste)

        # Signals
        self.connect("realize", self._on_realize)
        self.terminal.connect("contents-changed", self._on_contents_changed)
        self.terminal.connect("key-press-event", self._on_terminal_key_press)
        self.terminal.connect("button-press-event", self._on_terminal_button_press)
        self._password_entry.connect("activate", self._on_password_activate)
        self._password_entry.connect("key-press-event", self._on_password_key_press)

        self._spawn_child(command_argv)

    def _on_realize(self, *_args):
        # Use GTK theme colors for terminal fg/bg so it matches Cinnamon themes.
        ctx = self.terminal.get_style_context()
        state = Gtk.StateFlags.NORMAL
        try:
            fg = ctx.get_color(state)
        except Exception:
            fg = Gdk.RGBA(0.9, 0.9, 0.9, 1.0)

        bg = None
        try:
            # Gtk3: get_background_color exists but is deprecated; still usable.
            bg = ctx.get_background_color(state)
        except Exception:
            bg = Gdk.RGBA(0.0, 0.0, 0.0, 1.0)

        self.terminal.set_color_foreground(fg)
        self.terminal.set_color_background(bg)
        self.terminal.set_color_cursor(fg)

    def _apply_font_from_cinnamon_settings(self) -> None:
        font_name = None
        for schema in ("org.cinnamon.desktop.interface", "org.gnome.desktop.interface"):
            try:
                settings = Gio.Settings.new(schema)
            except Exception:
                continue
            if settings.list_keys() and "monospace-font-name" in settings.list_keys():
                try:
                    font_name = settings.get_string("monospace-font-name")
                    break
                except Exception:
                    pass

        if not font_name:
            return

        try:
            desc = Pango.FontDescription(font_name)
            if desc.get_family():
                self.terminal.set_font(desc)
        except Exception:
            return

    def _apply_icon(self) -> None:
        # Prefer icon theme name; fallback to bundled SVG file.
        icon_name = "org.vistula.Terminal"

        try:
            # Ensure our local hicolor icons are discoverable when running uninstalled.
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            icons_dir = os.path.join(root, "data", "icons")
            theme = Gtk.IconTheme.get_default()
            theme.append_search_path(icons_dir)
        except Exception:
            pass

        try:
            self.set_icon_name(icon_name)
            return
        except Exception:
            pass

        try:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            icon_file = os.path.join(root, "data", "icons", "hicolor", "scalable", "apps", f"{icon_name}.svg")
            if os.path.exists(icon_file):
                self.set_icon_from_file(icon_file)
        except Exception:
            pass

    def _spawn_child(self, command_argv: Optional[list[str]] = None) -> None:
        cwd = os.environ.get("PWD") or os.path.expanduser("~")

        if command_argv and len(command_argv) > 0:
            argv = command_argv
        else:
            shell = os.environ.get("SHELL") or "/bin/bash"
            argv = [shell, "-l"]

        envv = [f"{k}={v}" for k, v in os.environ.items()]

        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            cwd,
            argv,
            envv,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self._on_spawned,
        )

    def _on_spawned(self, _terminal: Vte.Terminal, task: Gio.AsyncResult):
        try:
            self.terminal.spawn_async_finish(task)
        except Exception as exc:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=self._tr.t("error.spawn.title", "Nie udało się uruchomić powłoki."),
            )
            dialog.format_secondary_text(str(exc))
            dialog.run()
            dialog.destroy()

    def _on_copy(self, *_args):
        self.terminal.copy_clipboard()
        return True

    def _on_paste(self, *_args):
        self.terminal.paste_clipboard()
        return True

    def _enter_password_mode(self):
        if self._password.active:
            return
        self._password.active = True
        self._password_entry.set_text("")
        self._password_revealer.set_reveal_child(True)
        self._password_entry.grab_focus()

    def _exit_password_mode(self):
        if not self._password.active:
            return
        self._password.active = False
        self._password_entry.set_text("")
        self._password_revealer.set_reveal_child(False)
        self.terminal.grab_focus()

    def _looks_like_password_prompt(self) -> bool:
        # Heuristic: inspect the last visible line up to cursor.
        try:
            cursor_col, cursor_row = self.terminal.get_cursor_position()
        except Exception:
            return False

        cols = max(1, self.terminal.get_column_count())
        row = max(0, cursor_row)

        # Avoid re-triggering forever on same row.
        if self._password.last_trigger_row == row:
            return False

        try:
            text, _attrs = self.terminal.get_text_range(
                row,
                0,
                row,
                cols,
                lambda *_a: True,
            )
        except Exception:
            return False

        line = (text or "").strip("\r\n")
        if PASSWORD_PROMPT_RE.search(line):
            self._password.last_trigger_row = row
            return True
        return False

    def _on_contents_changed(self, *_args):
        if self._password.active:
            return

        # Debounce: schedule check in idle so cursor position updated.
        GLib.idle_add(self._maybe_enter_password_mode)

    def _maybe_enter_password_mode(self):
        if self._password.active:
            return False
        if self._looks_like_password_prompt():
            self._enter_password_mode()
        return False

    def _on_password_activate(self, _entry: Gtk.Entry):
        value = self._password_entry.get_text() or ""
        # Send buffered password + newline to the child.
        self.terminal.feed_child((value + "\n").encode("utf-8"))
        self._exit_password_mode()

    def _on_password_key_press(self, _entry: Gtk.Entry, event: Gdk.EventKey):
        if event.keyval == Gdk.KEY_Escape:
            self._exit_password_mode()
            return True
        return False

    def _on_terminal_key_press(self, _terminal: Vte.Terminal, event: Gdk.EventKey):
        # If a password prompt just appeared, moving focus to the entry is enough.
        if not self._password.active and event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            # After pressing enter, the prompt may show up; next contents-changed will handle it.
            return False

        if not self._password.active and self._looks_like_password_prompt():
            self._enter_password_mode()
            return True

        return False

    def _on_terminal_button_press(self, _terminal: Vte.Terminal, event: Gdk.EventButton):
        # 3 = prawy przycisk: menu kopiuj/wklej
        if event.button == 3:
            self._show_context_menu(event)
            return True

        # 2 = środkowy przycisk: wklej PRIMARY (klasyczne X11/Wayland)
        if event.button == 2:
            try:
                self.terminal.paste_primary()
            except Exception:
                self.terminal.paste_clipboard()
            return True

        return False

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()

        item_copy = Gtk.MenuItem(label=self._tr.t("menu.copy", "Kopiuj"))
        item_paste = Gtk.MenuItem(label=self._tr.t("menu.paste", "Wklej"))

        item_copy.connect("activate", lambda *_a: self.terminal.copy_clipboard())
        item_paste.connect("activate", lambda *_a: self.terminal.paste_clipboard())

        # Sensowne stany (kopiuj tylko gdy jest zaznaczenie)
        try:
            item_copy.set_sensitive(bool(self.terminal.get_has_selection()))
        except Exception:
            pass

        menu.append(item_copy)
        menu.append(item_paste)
        menu.show_all()

        # GTK3
        try:
            menu.popup_at_pointer(event)
        except Exception:
            menu.popup(None, None, None, None, event.button, event.time)


class VistulaTerminalApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.vistula.Terminal", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        try:
            self.set_default_icon_name("org.vistula.Terminal")
        except Exception:
            pass

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = VistulaTerminalWindow(self)
        win.show_all()
        win.present()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine):
        argv = command_line.get_arguments()[1:]

        if "--version" in argv:
            command_line.print(f"{__version__}\n")
            return 0

        win = VistulaTerminalWindow(self, command_argv=argv if argv else None)
        win.show_all()
        win.present()
        return 0


def main(argv: list[str]) -> int:
    app = VistulaTerminalApp()
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
