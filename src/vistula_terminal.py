#!/usr/bin/env python3
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

try:
    import gi

    require_version = getattr(gi, "require_version", None)
    if require_version is None:
        raise ImportError("PyGObject (python3-gi) nie jest zainstalowany")

    gi.require_version("Gtk", "3.0")
    gi.require_version("Vte", "2.91")

    from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402
except Exception as exc:  # pragma: no cover
    print("Błąd: brak zależności do uruchomienia GUI terminala.")
    print("Zainstaluj: python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91")
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
        self.set_title("Vistula Terminal")
        self.set_default_size(860, 520)

        self._password = PasswordMode()

        self._overlay = Gtk.Overlay()
        self.add(self._overlay)

        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(10000)
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

        # Copy/paste shortcuts
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        accel.connect(Gdk.keyval_from_name("C"), Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0, self._on_copy)
        accel.connect(Gdk.keyval_from_name("V"), Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0, self._on_paste)

        # Signals
        self.connect("realize", self._on_realize)
        self.terminal.connect("contents-changed", self._on_contents_changed)
        self.terminal.connect("key-press-event", self._on_terminal_key_press)
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
                text="Nie udało się uruchomić powłoki.",
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


class VistulaTerminalApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.vistula.Terminal", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = VistulaTerminalWindow(self)
        win.show_all()
        win.present()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine):
        argv = command_line.get_arguments()[1:]
        win = VistulaTerminalWindow(self, command_argv=argv if argv else None)
        win.show_all()
        win.present()
        return 0


def main(argv: list[str]) -> int:
    app = VistulaTerminalApp()
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
