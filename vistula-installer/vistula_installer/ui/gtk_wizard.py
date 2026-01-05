from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from threading import Thread

from vistula_installer.core.config import AppConfig
from vistula_installer.core.executor import CommandExecutor
from vistula_installer.core.i18n import load_i18n, I18n
from vistula_installer.core.installer import (
    InstallerEngine,
    build_fstab_content,
    list_disks,
    list_partitions,
)
from vistula_installer.core.software import (
    SoftwareSelection,
    arch_packages_for_selection,
    flatpak_appids_for_selection,
)
from vistula_installer.core.themes import list_gtk_themes
from vistula_installer.core.network import list_wifi_networks
from vistula_installer.core.locales import list_supported_locales
from vistula_installer.core.flatpak import search_flatpak
from vistula_installer.core.timezones import list_timezones


log = logging.getLogger(__name__)


def run_gui(*, config: AppConfig) -> int:
    try:
        import gi  # type: ignore

        require_version = getattr(gi, "require_version", None)
        if require_version is None:
            raise RuntimeError(
                "PyGObject (python3-gi) is missing or broken: gi.require_version not found."
            )

        require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib, Gdk  # type: ignore[import-not-found]
    except Exception as e:
        print("GTK (PyGObject) not available:", e)
        print(
            "\nInstall (Debian/Ubuntu): sudo apt install python3-gi gir1.2-gtk-3.0\n"
            "Install (Arch): sudo pacman -S python-gobject gtk3\n"
        )
        return 2

    executor = CommandExecutor(dry_run=config.runtime.dry_run)

    state = WizardState(config=config, executor=executor)
    state.set_language(config.ui.language)

    # Make checkboxes discoverable even when unchecked (some themes hide the empty indicator).
    try:
        css = b"""
        .vistula-check check {
          border: 1px solid @theme_fg_color;
          background-color: @theme_base_color;
          border-radius: 2px;
          min-width: 16px;
          min-height: 16px;
          margin-right: 6px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except Exception:
        pass

    # Apply theme if configured (Cinnamon uses GTK themes; this keeps it consistent).
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # type: ignore

        if config.ui.gtk_theme:
            settings = Gtk.Settings.get_default()
            if settings is not None:
                settings.set_property("gtk-theme-name", config.ui.gtk_theme)
    except Exception:
        pass

    win = InstallerWindow(state=state)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


@dataclass
class WizardState:
    config: AppConfig
    executor: CommandExecutor
    i18n: I18n | None = None
    last_error: str | None = None

    def set_language(self, lang: str) -> None:
        self.config.ui.language = lang
        self.i18n = load_i18n(lang)
        self.config.save()

    def _(self, msgid: str) -> str:
        if self.i18n is None:
            return msgid
        return self.i18n.t(msgid)


class InstallerWindow:
    def __init__(self, *, state: WizardState):
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib  # type: ignore[import-not-found]

        self.Gtk = Gtk
        self.GLib = GLib
        self.state = state

        self.window = Gtk.Window(title=state._("VistulaOS Installer"))
        self.window.set_default_size(860, 520)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_border_width(12)
        self.window.add(vbox)

        self.header = Gtk.Label()
        self.header.set_xalign(0)
        vbox.pack_start(self.header, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(180)
        vbox.pack_start(self.stack, True, True, 0)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(nav, False, False, 0)

        self.busy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.busy_spinner = Gtk.Spinner()
        self.busy_label = Gtk.Label(label=state._("Loading..."))
        self.busy_box.pack_start(self.busy_spinner, False, False, 0)
        self.busy_box.pack_start(self.busy_label, False, False, 0)
        self.busy_box.set_no_show_all(True)
        nav.pack_start(self.busy_box, False, False, 0)

        self.btn_back = Gtk.Button(label=state._("Back"))
        self.btn_next = Gtk.Button(label=state._("Next"))
        self.btn_back.connect("clicked", self.on_back)
        self.btn_next.connect("clicked", self.on_next)
        nav.pack_start(self.btn_back, False, False, 0)
        nav.pack_end(self.btn_next, False, False, 0)

        self.pages: list[WizardPage] = []
        self._build_pages()
        self._go_to(0)

        self._busy_count = 0

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        """Show loader and disable navigation while busy."""
        if busy:
            self._busy_count += 1
        else:
            self._busy_count = max(0, self._busy_count - 1)

        is_busy = self._busy_count > 0
        if message:
            self.busy_label.set_text(message)
        else:
            self.busy_label.set_text(self.state._("Loading..."))

        self.btn_back.set_sensitive(not is_busy and self.current_idx > 0)
        # If we're on FinishPage, Next is Close; still disable while busy.
        self.btn_next.set_sensitive(not is_busy and not isinstance(self.pages[self.current_idx], ProgressPage))

        if is_busy:
            self.busy_box.show()
            self.busy_spinner.start()
        else:
            self.busy_spinner.stop()
            self.busy_box.hide()

    def rebuild_ui(self) -> None:
        """Rebuild widgets so every label reflects current language.

        We sync current values to config first to avoid losing user input.
        """
        try:
            for p in self.pages:
                sync = getattr(p, "sync_to_config", None)
                if callable(sync):
                    sync()
        except Exception:
            pass

        current_idx = getattr(self, "current_idx", 0)
        for child in self.stack.get_children():
            self.stack.remove(child)
        self._build_pages()
        self.window.set_title(self.state._("VistulaOS Installer"))
        self._go_to(current_idx)
        self.show_all()

    def connect(self, *args, **kwargs):
        return self.window.connect(*args, **kwargs)

    def show_all(self):
        self.window.show_all()

    def _build_pages(self) -> None:
        s = self.state
        self.pages = [
            WelcomePage(self, s),
            LanguagePage(self, s),
            LocalePage(self, s),
            NetworkPage(self, s),
            DiskPage(self, s),
            UserPage(self, s),
            SoftwarePage(self, s),
            SummaryPage(self, s),
            ProgressPage(self, s),
            FinishPage(self, s),
        ]
        for p in self.pages:
            self.stack.add_named(p.widget, p.name)

    def _go_to(self, idx: int) -> None:
        idx = max(0, min(idx, len(self.pages) - 1))
        self.current_idx = idx
        page = self.pages[idx]
        page.on_show()
        self.stack.set_visible_child(page.widget)
        self.header.set_text(page.title)

        self.btn_back.set_sensitive(idx > 0 and not isinstance(page, ProgressPage))
        if isinstance(page, FinishPage):
            self.btn_next.set_label(self.state._("Close"))
        elif isinstance(page, ProgressPage):
            self.btn_next.set_sensitive(False)
            self.btn_next.set_label(self.state._("Next"))
        else:
            self.btn_next.set_sensitive(True)
            self.btn_next.set_label(self.state._("Next"))

    def on_back(self, _btn) -> None:
        # Avoid double-clicks; show a loader during navigation.
        self.set_busy(True)

        def do_nav() -> None:
            try:
                self._go_to(self.current_idx - 1)
            finally:
                self.set_busy(False)

        self.GLib.idle_add(do_nav)

    def on_next(self, _btn) -> None:
        page = self.pages[self.current_idx]
        if isinstance(page, FinishPage):
            self.window.close()
            return

        self.set_busy(True)

        def do_next() -> None:
            try:
                ok, msg = page.validate()
                if not ok:
                    self._show_error(msg)
                    return

                page.on_next()
                self._go_to(self.current_idx + 1)
            finally:
                self.set_busy(False)

        self.GLib.idle_add(do_next)

    def _show_error(self, message: str) -> None:
        Gtk = self.Gtk
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.run()
        dialog.destroy()


class WizardPage:
    name: str = ""
    title: str = ""

    def __init__(self, window: InstallerWindow, state: WizardState):
        self.window = window
        self.state = state
        self.widget = self.build()

    def build(self):
        raise NotImplementedError

    def _style_checkbox(self, cb) -> None:
        try:
            cb.get_style_context().add_class("vistula-check")
        except Exception:
            pass

    def on_show(self) -> None:
        pass

    def validate(self) -> tuple[bool, str]:
        return True, ""

    def on_next(self) -> None:
        pass


class WelcomePage(WizardPage):
    name = "welcome"

    @property
    def title(self) -> str:
        return self.state._("Welcome")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        lbl = Gtk.Label()
        lbl.set_xalign(0)
        lbl.set_line_wrap(True)
        lbl.set_text(
            self.state._(
                "This wizard will guide you through installing VistulaOS."
            )
        )
        box.pack_start(lbl, False, False, 0)

        warn = Gtk.Label()
        warn.set_xalign(0)
        warn.set_line_wrap(True)
        warn.set_text(
            self.state._(
                "Warning: Installation can erase disks. Use dry-run to preview steps."
            )
        )
        box.pack_start(warn, False, False, 0)

        # Optional GTK theme selector (works well with Cinnamon themes).
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        theme_row.pack_start(Gtk.Label(label=self.state._("GTK theme:")), False, False, 0)
        self.theme_combo = Gtk.ComboBoxText()
        self.theme_combo.append("", self.state._("System default"))
        for t in list_gtk_themes():
            self.theme_combo.append(t, t)
        self.theme_combo.set_active_id(self.state.config.ui.gtk_theme or "")
        self.theme_combo.connect("changed", self.on_theme_changed)
        theme_row.pack_start(self.theme_combo, False, False, 0)
        box.pack_start(theme_row, False, False, 0)

        return box

    def on_theme_changed(self, _combo) -> None:
        theme = self.theme_combo.get_active_id() or None
        if theme == "":
            theme = None
        self.state.config.ui.gtk_theme = theme
        self.state.config.save()
        # Apply immediately if possible.
        try:
            settings = self.window.Gtk.Settings.get_default()
            if settings is not None and theme:
                settings.set_property("gtk-theme-name", theme)
        except Exception:
            pass


class LanguagePage(WizardPage):
    name = "language"

    @property
    def title(self) -> str:
        return self.state._("Language")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.pack_start(row, False, False, 0)

        row.pack_start(Gtk.Label(label=self.state._("Select language:")), False, False, 0)

        self.combo = Gtk.ComboBoxText()
        self.combo.append("pl", "Polski")
        self.combo.append("en", "English")
        self.combo.append("es", "Español")
        self.combo.append("pt", "Português")
        self.combo.append("fr", "Français")
        self.combo.append("ru", "Русский")
        self.combo.append("de", "Deutsch")
        self.combo.append("zh", "中文")
        self.combo.append("ja", "日本語")
        self.combo.set_active_id(self.state.config.ui.language)
        self.combo.connect("changed", self.on_changed)
        row.pack_start(self.combo, False, False, 0)

        info = Gtk.Label(label=self.state._("You can change language later."))
        info.set_xalign(0)
        box.pack_start(info, False, False, 0)

        return box

    def on_changed(self, _combo) -> None:
        lang = self.combo.get_active_id() or "pl"
        self.state.set_language(lang)
        # Rebuild so the whole installer changes language immediately.
        self.window.rebuild_ui()


class LocalePage(WizardPage):
    name = "locale"

    @property
    def title(self) -> str:
        return self.state._("Language & Region")

    def build(self):
        Gtk = self.window.Gtk
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)

        self.locale = Gtk.ComboBoxText()
        self.locale.append("", self.state._("Loading...") )
        self.locale.set_active_id("")
        self._locale_loaded = False

        self._kbd_autoset = True
        self._tz_loaded = False

        self.kb = Gtk.ComboBoxText()
        self.kb.append("pl", "Polski (pl)")
        self.kb.append("us", "US (us)")
        self.kb.append("de", "Deutsch (de)")
        self.kb.append("fr", "Français (fr)")
        self.kb.append("es", "Español (es)")
        self.kb.append("pt", "Português (pt)")
        self.kb.append("ru", "Русский (ru)")
        self.kb.append("jp", "日本語 (jp)")
        self.kb.set_active_id(self.state.config.install.keyboard_layout)
        self.kb.connect("changed", self.on_kb_changed)

        self.tz = Gtk.ComboBoxText()
        self.tz.append("", self.state._("Loading...") )
        self.tz.set_active_id("")

        self.chk_all_locales = Gtk.CheckButton(label=self.state._("Generate all locales (Arch)"))
        self.chk_all_locales.set_active(self.state.config.install.generate_all_locales_arch)
        self._style_checkbox(self.chk_all_locales)

        grid.attach(Gtk.Label(label=self.state._("System locale")), 0, 0, 1, 1)
        grid.attach(self.locale, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=self.state._("Keyboard layout")), 0, 1, 1, 1)
        grid.attach(self.kb, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label=self.state._("Timezone")), 0, 2, 1, 1)
        grid.attach(self.tz, 1, 2, 1, 1)
        grid.attach(self.chk_all_locales, 1, 3, 1, 1)

        self.locale.connect("changed", self.on_locale_changed)
        return grid

    def on_show(self) -> None:
        if getattr(self, "_locale_loaded", False):
            # Still ensure tz loaded.
            self._ensure_timezones()
            return

        self.locale.remove_all()
        locales = list_supported_locales(self.state.executor, utf8_only=True)

        # Ensure commonly expected locales exist in the list (even if host is minimal).
        must = [
            "pl_PL.UTF-8",
            "en_US.UTF-8",
            "es_ES.UTF-8",
            "pt_PT.UTF-8",
            "fr_FR.UTF-8",
            "ru_RU.UTF-8",
            "de_DE.UTF-8",
            "zh_CN.UTF-8",
            "ja_JP.UTF-8",
        ]
        for m in must:
            if m not in locales:
                locales.append(m)
        locales = sorted(set(locales), key=str.casefold)

        for loc in locales:
            self.locale.append(loc, loc)

        active = self.state.config.install.locale
        if active in locales:
            self.locale.set_active_id(active)
        else:
            self.locale.set_active_id("pl_PL.UTF-8" if "pl_PL.UTF-8" in locales else locales[0])

        self._locale_loaded = True
        self._ensure_timezones()

    def _ensure_timezones(self) -> None:
        if getattr(self, "_tz_loaded", False):
            return
        self.tz.remove_all()
        zones = list_timezones(self.state.executor)
        if not zones:
            zones = [self.state.config.install.timezone]
        for z in zones:
            self.tz.append(z, z)
        active = self.state.config.install.timezone
        if active in zones:
            self.tz.set_active_id(active)
        else:
            self.tz.set_active_id("Europe/Warsaw" if "Europe/Warsaw" in zones else zones[0])
        self._tz_loaded = True

    def on_kb_changed(self, _combo) -> None:
        # If user changed it manually, stop auto-binding to locale.
        self._kbd_autoset = False

    def on_locale_changed(self, _combo) -> None:
        if not getattr(self, "_kbd_autoset", True):
            return

        loc = (self.locale.get_active_id() or "").lower()
        # Map locale -> XKB layout
        mapping = {
            "pl": "pl",
            "en": "us",
            "de": "de",
            "fr": "fr",
            "es": "es",
            "pt": "pt",
            "ru": "ru",
            "ja": "jp",
            "zh": "us",
        }
        prefix = loc.split("_")[0] if loc else ""
        layout = mapping.get(prefix)
        if layout:
            self.kb.set_active_id(layout)

    def on_next(self) -> None:
        self.state.config.install.locale = self.locale.get_active_id() or "pl_PL.UTF-8"
        self.state.config.install.keyboard_layout = self.kb.get_active_id() or "pl"
        self.state.config.install.timezone = self.tz.get_active_id() or "Europe/Warsaw"
        self.state.config.install.generate_all_locales_arch = bool(self.chk_all_locales.get_active())
        self.state.config.save()

    def sync_to_config(self) -> None:
        self.on_next()


class NetworkPage(WizardPage):
    name = "network"

    @property
    def title(self) -> str:
        return self.state._("Network")

    def build(self):
        Gtk = self.window.Gtk
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)

        self.chk_nm = Gtk.CheckButton(label=self.state._("Enable NetworkManager"))
        self.chk_nm.set_active(self.state.config.install.enable_networkmanager)
        self._style_checkbox(self.chk_nm)

        self.ent_ssid = Gtk.Entry(text=self.state.config.install.wifi_ssid)
        self.ent_wifi_pass = Gtk.Entry()
        self.ent_wifi_pass.set_visibility(False)

        self.btn_scan = Gtk.Button(label=self.state._("Scan Wi-Fi"))
        self.btn_scan.connect("clicked", self.on_scan_clicked)
        self.combo_wifi = Gtk.ComboBoxText()
        self.combo_wifi.append("", self.state._("Select network..."))
        self.combo_wifi.set_active_id("")
        self.combo_wifi.connect("changed", self.on_wifi_selected)

        grid.attach(self.chk_nm, 0, 0, 2, 1)
        grid.attach(self.btn_scan, 0, 1, 1, 1)
        grid.attach(self.combo_wifi, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label=self.state._("Wi-Fi SSID (optional)")), 0, 2, 1, 1)
        grid.attach(self.ent_ssid, 1, 2, 1, 1)
        grid.attach(Gtk.Label(label=self.state._("Wi-Fi password")), 0, 3, 1, 1)
        grid.attach(self.ent_wifi_pass, 1, 3, 1, 1)
        return grid

    def on_show(self) -> None:
        # Auto-scan best-effort; user can rescan.
        self._scan_wifi()

    def on_scan_clicked(self, _btn) -> None:
        self._scan_wifi()

    def _scan_wifi(self) -> None:
        # nmcli rescan can take a moment; run it off the UI thread.
        self.combo_wifi.remove_all()
        self.combo_wifi.append("", self.state._("Select network..."))
        self.combo_wifi.set_active_id("")

        self.window.set_busy(True, self.state._("Scanning Wi-Fi..."))

        def worker() -> None:
            nets = list_wifi_networks(self.state.executor)

            def ui_update() -> None:
                try:
                    self.combo_wifi.remove_all()
                    self.combo_wifi.append("", self.state._("Select network..."))
                    for n in nets:
                        suffix = []
                        if n.signal is not None:
                            suffix.append(f"{n.signal}%")
                        if n.security:
                            suffix.append(n.security)
                        meta = f" ({', '.join(suffix)})" if suffix else ""
                        self.combo_wifi.append(n.ssid, f"{n.ssid}{meta}")
                    self.combo_wifi.set_active_id("")
                finally:
                    self.window.set_busy(False)

            self.window.GLib.idle_add(ui_update)

        Thread(target=worker, daemon=True).start()

    def on_wifi_selected(self, _combo) -> None:
        ssid = self.combo_wifi.get_active_id() or ""
        if ssid:
            self.ent_ssid.set_text(ssid)

    def on_next(self) -> None:
        self.state.config.install.enable_networkmanager = bool(self.chk_nm.get_active())
        self.state.config.install.wifi_ssid = self.ent_ssid.get_text().strip()
        self.state.config.install.wifi_password = self.ent_wifi_pass.get_text()
        self.state.config.save()

    def sync_to_config(self) -> None:
        self.on_next()


class DiskPage(WizardPage):
    name = "disk"

    @property
    def title(self) -> str:
        return self.state._("Disk")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        self.combo = Gtk.ComboBoxText()
        box.pack_start(Gtk.Label(label=self.state._("Target disk:")), False, False, 0)
        box.pack_start(self.combo, False, False, 0)

        box.pack_start(Gtk.Label(label=self.state._("Installation mode:")), False, False, 0)
        self.rb_erase = Gtk.RadioButton.new_with_label_from_widget(None, self.state._("Use entire disk (erase)"))
        self.rb_manual = Gtk.RadioButton.new_with_label_from_widget(self.rb_erase, self.state._("Manual partitioning"))
        self.rb_erase.connect("toggled", self.on_mode_changed)
        self.rb_manual.connect("toggled", self.on_mode_changed)
        box.pack_start(self.rb_erase, False, False, 0)
        box.pack_start(self.rb_manual, False, False, 0)

        self.manual_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.manual_grid.set_margin_top(6)

        self.combo_root = Gtk.ComboBoxText()
        self.combo_efi = Gtk.ComboBoxText()
        self.combo_home = Gtk.ComboBoxText()
        self.combo_swap = Gtk.ComboBoxText()

        # Populated on_show
        self._parts_meta: dict[str, object] = {}

        self.chk_fmt_root = Gtk.CheckButton(label=self.state._("Format root partition (ext4)"))
        self.chk_fmt_efi = Gtk.CheckButton(label=self.state._("Format EFI partition (vfat)"))
        self.chk_fmt_home = Gtk.CheckButton(label=self.state._("Format home partition (ext4)"))
        self.chk_fmt_swap = Gtk.CheckButton(label=self.state._("Format swap partition"))

        for cb in (self.chk_fmt_root, self.chk_fmt_efi, self.chk_fmt_home, self.chk_fmt_swap):
            self._style_checkbox(cb)

        self.manual_grid.attach(Gtk.Label(label=self.state._("Root partition (/):")), 0, 0, 1, 1)
        self.manual_grid.attach(self.combo_root, 1, 0, 1, 1)
        self.manual_grid.attach(self.chk_fmt_root, 2, 0, 1, 1)

        self.manual_grid.attach(Gtk.Label(label=self.state._("EFI partition (/boot/efi):")), 0, 1, 1, 1)
        self.manual_grid.attach(self.combo_efi, 1, 1, 1, 1)
        self.manual_grid.attach(self.chk_fmt_efi, 2, 1, 1, 1)

        self.manual_grid.attach(Gtk.Label(label=self.state._("Home partition (/home) (optional):")), 0, 2, 1, 1)
        self.manual_grid.attach(self.combo_home, 1, 2, 1, 1)
        self.manual_grid.attach(self.chk_fmt_home, 2, 2, 1, 1)

        self.manual_grid.attach(Gtk.Label(label=self.state._("Swap partition (optional):")), 0, 3, 1, 1)
        self.manual_grid.attach(self.combo_swap, 1, 3, 1, 1)
        self.manual_grid.attach(self.chk_fmt_swap, 2, 3, 1, 1)

        # Auto-tune format defaults when user changes selection.
        for combo in (self.combo_root, self.combo_efi, self.combo_home, self.combo_swap):
            combo.connect("changed", self.on_manual_partition_changed)

        box.pack_start(self.manual_grid, False, False, 0)

        # Initialize from config
        if self.state.config.install.erase_disk:
            self.rb_erase.set_active(True)
        else:
            self.rb_manual.set_active(True)

        self.chk_fmt_root.set_active(self.state.config.install.format_root)
        self.chk_fmt_efi.set_active(self.state.config.install.format_efi)
        self.chk_fmt_home.set_active(self.state.config.install.format_home)
        self.chk_fmt_swap.set_active(self.state.config.install.format_swap)

        self.on_mode_changed(None)

        return box

    @staticmethod
    def _parse_size_bytes(size: str) -> int:
        # lsblk default SIZE is human-readable (e.g., 953.9G). Parse best-effort.
        s = (size or "").strip()
        if not s:
            return 0
        m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([KMGTP]?)B?$", s, re.IGNORECASE)
        if not m:
            return 0
        num = float(m.group(1))
        unit = (m.group(2) or "").upper()
        mul = {
            "": 1,
            "K": 1024,
            "M": 1024**2,
            "G": 1024**3,
            "T": 1024**4,
            "P": 1024**5,
        }.get(unit, 1)
        return int(num * mul)

    def _fstype_for(self, path: str) -> str:
        p = self._parts_meta.get(path)
        try:
            return str(getattr(p, "fstype", "") or "")
        except Exception:
            return ""

    def on_manual_partition_changed(self, _combo) -> None:
        # Only auto-adjust format flags when in manual mode.
        if not self.rb_manual.get_active():
            return
        self._autofill_format_flags()

    def _autofill_format_flags(self) -> None:
        # Best-effort defaults: if filesystem already matches expected, default to NOT formatting.
        def want_format(selected: str, expected: str) -> bool:
            if not selected:
                return False
            fstype = self._fstype_for(selected).lower()
            expected_l = expected.lower()
            if not fstype:
                return True
            if expected_l == "vfat":
                return fstype not in {"vfat", "fat", "fat16", "fat32"}
            return fstype != expected_l

        root = self.combo_root.get_active_id() or ""
        efi = self.combo_efi.get_active_id() or ""
        home = self.combo_home.get_active_id() or ""
        swap = self.combo_swap.get_active_id() or ""

        # Only set if user hasn't explicitly persisted a choice yet.
        cfg = self.state.config.install
        if cfg.erase_disk:
            return

        self.chk_fmt_root.set_active(want_format(root, "ext4"))
        self.chk_fmt_efi.set_active(want_format(efi, "vfat"))
        self.chk_fmt_home.set_active(want_format(home, "ext4"))
        self.chk_fmt_swap.set_active(want_format(swap, "swap"))

    def _autoselect_partitions_if_empty(self, parts) -> None:
        cfg = self.state.config.install
        if cfg.erase_disk:
            return

        # Respect existing config selections.
        if cfg.root_partition or cfg.efi_partition or cfg.home_partition or cfg.swap_partition:
            return

        # Compute candidates.
        is_efi = os.path.exists("/sys/firmware/efi")

        def bytes_of(p) -> int:
            return self._parse_size_bytes(getattr(p, "size", "") or "")

        def fstype_of(p) -> str:
            return str(getattr(p, "fstype", "") or "").lower()

        unmounted = [p for p in parts if not (getattr(p, "mountpoint", "") or "").strip()]
        candidates = unmounted if unmounted else list(parts)

        efi_cands = [p for p in candidates if fstype_of(p) in {"vfat", "fat", "fat16", "fat32"}]
        swap_cands = [p for p in candidates if fstype_of(p) == "swap"]
        linux_cands = [
            p
            for p in candidates
            if fstype_of(p) in {"ext4", "btrfs", "xfs", "f2fs", "ext3", "ext2"} or fstype_of(p) == ""
        ]

        efi = None
        if is_efi and efi_cands:
            # Prefer small VFAT (typical ESP)
            efi = sorted(efi_cands, key=lambda p: bytes_of(p))[0]

        swap = None
        if swap_cands:
            swap = sorted(swap_cands, key=lambda p: bytes_of(p), reverse=True)[0]

        chosen = set()
        if efi:
            chosen.add(getattr(efi, "path", ""))
        if swap:
            chosen.add(getattr(swap, "path", ""))

        linux_cands2 = [p for p in linux_cands if getattr(p, "path", "") not in chosen]
        linux_cands2.sort(key=lambda p: bytes_of(p), reverse=True)

        root = linux_cands2[0] if linux_cands2 else None
        home = linux_cands2[1] if len(linux_cands2) > 1 else None

        if root:
            self.combo_root.set_active_id(getattr(root, "path", ""))
        if efi:
            self.combo_efi.set_active_id(getattr(efi, "path", ""))
        if home:
            self.combo_home.set_active_id(getattr(home, "path", ""))
        if swap:
            self.combo_swap.set_active_id(getattr(swap, "path", ""))

        self._autofill_format_flags()

    def on_mode_changed(self, _btn) -> None:
        manual = bool(self.rb_manual.get_active())
        self.manual_grid.set_sensitive(manual)
        self.manual_grid.set_visible(manual)

    def on_show(self) -> None:
        # Refresh disk list
        self.combo.remove_all()
        disks = list_disks(self.state.executor)
        for d in disks:
            label = f"{d.path}  ({d.size})  {d.model}".strip()
            self.combo.append(d.path, label)

        if self.state.config.install.target_disk:
            self.combo.set_active_id(self.state.config.install.target_disk)
        else:
            self.combo.set_active(0)

        # Refresh partitions list (filtered by selected disk)
        disk = self.combo.get_active_id() or self.state.config.install.target_disk or ""
        prefix = disk
        if "nvme" in disk or "mmcblk" in disk:
            prefix = disk + "p"

        parts = [p for p in list_partitions(self.state.executor) if (prefix and p.path.startswith(prefix))]
        # Put unmounted first
        parts.sort(key=lambda p: (p.mountpoint != "", p.path))

        self._parts_meta = {p.path: p for p in parts}

        def fill(combo, *, allow_none: bool) -> None:
            combo.remove_all()
            if allow_none:
                combo.append("", self.state._("None"))
                combo.set_active_id("")
            for p in parts:
                extra = []
                if p.fstype:
                    extra.append(p.fstype)
                if p.label:
                    extra.append(p.label)
                if p.mountpoint:
                    extra.append(f"mounted:{p.mountpoint}")
                suffix = (" | " + ", ".join(extra)) if extra else ""
                combo.append(p.path, f"{p.path} ({p.size}){suffix}")

        fill(self.combo_root, allow_none=False)
        fill(self.combo_efi, allow_none=True)
        fill(self.combo_home, allow_none=True)
        fill(self.combo_swap, allow_none=True)

        cfg = self.state.config.install
        if cfg.root_partition:
            self.combo_root.set_active_id(cfg.root_partition)
        if cfg.efi_partition:
            self.combo_efi.set_active_id(cfg.efi_partition)
        if cfg.home_partition:
            self.combo_home.set_active_id(cfg.home_partition)
        if cfg.swap_partition:
            self.combo_swap.set_active_id(cfg.swap_partition)

        # Auto-pick sane defaults only when manual mode and config is empty.
        self._autoselect_partitions_if_empty(parts)

        # If user has selections, still update format defaults based on filesystem type.
        if not cfg.erase_disk:
            self._autofill_format_flags()

    def validate(self) -> tuple[bool, str]:
        disk = self.combo.get_active_id()
        if not disk:
            return False, self.state._("Please select a target disk.")

        if self.rb_erase.get_active():
            return True, ""

        root = self.combo_root.get_active_id() or ""
        if not root:
            return False, self.state._("Please select a root partition.")

        is_efi = os.path.exists("/sys/firmware/efi")
        efi = self.combo_efi.get_active_id() or ""
        if is_efi and not efi:
            return False, self.state._("Please select an EFI partition for UEFI systems.")

        home = self.combo_home.get_active_id() or ""
        swap = self.combo_swap.get_active_id() or ""

        # Basic sanity: don't allow duplicates
        chosen = [p for p in [root, efi, home, swap] if p]
        if len(set(chosen)) != len(chosen):
            return False, self.state._("Selected partitions must be different.")
        return True, ""

    def on_next(self) -> None:
        self.state.config.install.target_disk = self.combo.get_active_id()

        cfg = self.state.config.install
        cfg.erase_disk = bool(self.rb_erase.get_active())

        cfg.root_partition = self.combo_root.get_active_id() or ""
        cfg.efi_partition = self.combo_efi.get_active_id() or ""
        cfg.home_partition = self.combo_home.get_active_id() or ""
        cfg.swap_partition = self.combo_swap.get_active_id() or ""
        cfg.format_root = bool(self.chk_fmt_root.get_active())
        cfg.format_efi = bool(self.chk_fmt_efi.get_active())
        cfg.format_home = bool(self.chk_fmt_home.get_active())
        cfg.format_swap = bool(self.chk_fmt_swap.get_active())
        self.state.config.save()

    def sync_to_config(self) -> None:
        self.on_next()


class UserPage(WizardPage):
    name = "user"

    @property
    def title(self) -> str:
        return self.state._("User")

    def build(self):
        Gtk = self.window.Gtk
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)

        self.ent_hostname = Gtk.Entry(text=self.state.config.install.hostname)
        self.ent_user = Gtk.Entry(text=self.state.config.install.username)
        self.ent_pass = Gtk.Entry()
        self.ent_pass.set_visibility(False)
        self.ent_pass2 = Gtk.Entry()
        self.ent_pass2.set_visibility(False)

        grid.attach(Gtk.Label(label=self.state._("Hostname")), 0, 0, 1, 1)
        grid.attach(self.ent_hostname, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=self.state._("Username")), 0, 1, 1, 1)
        grid.attach(self.ent_user, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label=self.state._("Password")), 0, 2, 1, 1)
        grid.attach(self.ent_pass, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label=self.state._("Repeat password")), 0, 3, 1, 1)
        grid.attach(self.ent_pass2, 1, 3, 1, 1)

        return grid

    def validate(self) -> tuple[bool, str]:
        u = self.ent_user.get_text().strip()
        h = self.ent_hostname.get_text().strip()
        p1 = self.ent_pass.get_text()
        p2 = self.ent_pass2.get_text()

        if not h:
            return False, self.state._("Hostname is required.")
        if not u:
            return False, self.state._("Username is required.")
        if not p1:
            return False, self.state._("Password is required.")
        if p1 != p2:
            return False, self.state._("Passwords do not match.")
        return True, ""

    def on_next(self) -> None:
        cfg = self.state.config.install
        cfg.hostname = self.ent_hostname.get_text().strip()
        cfg.username = self.ent_user.get_text().strip()
        cfg.password = self.ent_pass.get_text()
        self.state.config.save()

    def sync_to_config(self) -> None:
        # Don't overwrite password with empty when user didn't type.
        cfg = self.state.config.install
        cfg.hostname = self.ent_hostname.get_text().strip() or cfg.hostname
        cfg.username = self.ent_user.get_text().strip() or cfg.username
        if self.ent_pass.get_text():
            cfg.password = self.ent_pass.get_text()
        self.state.config.save()


class SoftwarePage(WizardPage):
    name = "software"

    @property
    def title(self) -> str:
        return self.state._("Drivers & Software")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        self.chk_nvidia = Gtk.CheckButton(label=self.state._("Install NVIDIA driver (Arch)") )
        self.chk_nvidia.set_active(self.state.config.install.driver_nvidia)
        self._style_checkbox(self.chk_nvidia)
        box.pack_start(self.chk_nvidia, False, False, 0)

        box.pack_start(Gtk.Label(label=self.state._("Optional bundles:")), False, False, 0)

        self.chk_gamers = Gtk.CheckButton(label=self.state._("Gamers"))
        self.chk_creators = Gtk.CheckButton(label=self.state._("Creators"))
        self.chk_accountants = Gtk.CheckButton(label=self.state._("Accountants"))
        self.chk_developers = Gtk.CheckButton(label=self.state._("Developers"))

        self.chk_gamers.set_active(self.state.config.install.profile_gamers)
        self.chk_creators.set_active(self.state.config.install.profile_creators)
        self.chk_accountants.set_active(self.state.config.install.profile_accountants)
        self.chk_developers.set_active(self.state.config.install.profile_developers)

        for cb in (self.chk_gamers, self.chk_creators, self.chk_accountants, self.chk_developers):
            self._style_checkbox(cb)

        for w in (self.chk_gamers, self.chk_creators, self.chk_accountants, self.chk_developers):
            box.pack_start(w, False, False, 0)

        # Bundle details (visible checkboxes)
        self._build_bundle_details(box)

        # What will be installed (updates live after user clicks)
        box.pack_start(Gtk.Label(label=self.state._("Will be installed:")), False, False, 0)
        self.lbl_plan = Gtk.Label()
        self.lbl_plan.set_xalign(0)
        self.lbl_plan.set_line_wrap(True)
        box.pack_start(self.lbl_plan, False, False, 0)

        # Flatpak search (only when no bundle selected)
        self.flatpak_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.flatpak_box.set_border_width(6)
        self.flatpak_box.set_no_show_all(True)

        flatpak_title = Gtk.Label(label=self.state._("No bundle selected — search Flatpak"))
        flatpak_title.set_xalign(0)
        self.flatpak_box.pack_start(flatpak_title, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ent_flatpak = Gtk.Entry()
        self.ent_flatpak.set_placeholder_text(self.state._("Search term"))
        self.btn_flatpak = Gtk.Button(label=self.state._("Search"))
        self.btn_flatpak.connect("clicked", self.on_flatpak_search)
        row.pack_start(self.ent_flatpak, True, True, 0)
        row.pack_start(self.btn_flatpak, False, False, 0)
        self.flatpak_box.pack_start(row, False, False, 0)

        self.flatpak_results = Gtk.ListBox()
        self.flatpak_results.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flatpak_box.pack_start(self.flatpak_results, True, True, 0)

        self.lbl_selected = Gtk.Label()
        self.lbl_selected.set_xalign(0)
        self.flatpak_box.pack_start(self.lbl_selected, False, False, 0)

        box.pack_start(self.flatpak_box, True, True, 0)

        note = Gtk.Label()
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.set_text(
            self.state._(
                "Selected software will be installed via pacman (system packages) and/or Flatpak (apps), depending on availability."
            )
        )
        box.pack_start(note, False, False, 0)

        # React to bundle toggles
        for cb in (self.chk_gamers, self.chk_creators, self.chk_accountants, self.chk_developers):
            cb.connect("toggled", lambda *_: self._update_flatpak_visibility())
            cb.connect("toggled", lambda *_: self._refresh_planned_install_label())
        self.chk_nvidia.connect("toggled", lambda *_: self._refresh_planned_install_label())
        self._update_flatpak_visibility()
        self._refresh_selected_flatpaks_label()
        self._refresh_planned_install_label()
        return box

    def _build_bundle_details(self, box) -> None:
        Gtk = self.window.Gtk
        cfg = self.state.config.install

        suffix_flatpak = "Flatpak"
        suffix_system = self.state._("System (pacman)")

        self.gamers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.gamers_box.pack_start(Gtk.Label(label=self.state._("Gamers options:")), False, False, 0)
        self.cb_steam = Gtk.CheckButton(label=f"Steam ({suffix_flatpak})")
        self.cb_lutris = Gtk.CheckButton(label=f"Lutris ({suffix_flatpak})")
        self.cb_wine = Gtk.CheckButton(label=f"Wine/Winetricks ({suffix_system})")
        self.cb_mangohud = Gtk.CheckButton(label=f"MangoHud ({suffix_system})")
        self.cb_gamemode = Gtk.CheckButton(label=f"GameMode ({suffix_system})")
        self.cb_steam.set_active(cfg.gamers_steam)
        self.cb_lutris.set_active(cfg.gamers_lutris)
        self.cb_wine.set_active(cfg.gamers_wine)
        self.cb_mangohud.set_active(cfg.gamers_mangohud)
        self.cb_gamemode.set_active(cfg.gamers_gamemode)
        for cb in (self.cb_steam, self.cb_lutris, self.cb_wine, self.cb_mangohud, self.cb_gamemode):
            self._style_checkbox(cb)
        for w in (self.cb_steam, self.cb_lutris, self.cb_wine, self.cb_mangohud, self.cb_gamemode):
            self.gamers_box.pack_start(w, False, False, 0)

        self.creators_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.creators_box.pack_start(Gtk.Label(label=self.state._("Creators options:")), False, False, 0)
        self.cb_gimp = Gtk.CheckButton(label=f"GIMP ({suffix_flatpak})")
        self.cb_inkscape = Gtk.CheckButton(label=f"Inkscape ({suffix_flatpak})")
        self.cb_blender = Gtk.CheckButton(label=f"Blender ({suffix_flatpak})")
        self.cb_kdenlive = Gtk.CheckButton(label=f"Kdenlive ({suffix_flatpak})")
        self.cb_audacity = Gtk.CheckButton(label=f"Audacity ({suffix_flatpak})")
        self.cb_gimp.set_active(cfg.creators_gimp)
        self.cb_inkscape.set_active(cfg.creators_inkscape)
        self.cb_blender.set_active(cfg.creators_blender)
        self.cb_kdenlive.set_active(cfg.creators_kdenlive)
        self.cb_audacity.set_active(cfg.creators_audacity)
        for cb in (self.cb_gimp, self.cb_inkscape, self.cb_blender, self.cb_kdenlive, self.cb_audacity):
            self._style_checkbox(cb)
        for w in (self.cb_gimp, self.cb_inkscape, self.cb_blender, self.cb_kdenlive, self.cb_audacity):
            self.creators_box.pack_start(w, False, False, 0)

        self.accountants_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.accountants_box.pack_start(Gtk.Label(label=self.state._("Accountants options:")), False, False, 0)
        self.cb_lo = Gtk.CheckButton(label=f"LibreOffice ({suffix_flatpak})")
        self.cb_gnucash = Gtk.CheckButton(label=f"GnuCash ({suffix_flatpak})")
        self.cb_lo.set_active(cfg.accountants_libreoffice)
        self.cb_gnucash.set_active(cfg.accountants_gnucash)
        for cb in (self.cb_lo, self.cb_gnucash):
            self._style_checkbox(cb)
        for w in (self.cb_lo, self.cb_gnucash):
            self.accountants_box.pack_start(w, False, False, 0)

        self.developers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.developers_box.pack_start(Gtk.Label(label=self.state._("Developers options:")), False, False, 0)
        self.cb_git = Gtk.CheckButton(label=f"Git ({suffix_system})")
        self.cb_base = Gtk.CheckButton(label=f"base-devel ({suffix_system})")
        self.cb_py = Gtk.CheckButton(label=f"Python ({suffix_system})")
        self.cb_node = Gtk.CheckButton(label=f"Node.js + npm ({suffix_system})")
        self.cb_vscode = Gtk.CheckButton(label=f"{self.state._('Visual Studio Code')} ({suffix_flatpak})")
        self.cb_git.set_active(cfg.developers_git)
        self.cb_base.set_active(cfg.developers_base_devel)
        self.cb_py.set_active(cfg.developers_python)
        self.cb_node.set_active(cfg.developers_nodejs)
        self.cb_vscode.set_active(getattr(cfg, "developers_vscode", False))
        for cb in (self.cb_git, self.cb_base, self.cb_py, self.cb_node, self.cb_vscode):
            self._style_checkbox(cb)
        for w in (self.cb_git, self.cb_base, self.cb_py, self.cb_node, self.cb_vscode):
            self.developers_box.pack_start(w, False, False, 0)

        box.pack_start(self.gamers_box, False, False, 0)
        box.pack_start(self.creators_box, False, False, 0)
        box.pack_start(self.accountants_box, False, False, 0)
        box.pack_start(self.developers_box, False, False, 0)

        self._update_bundle_details_visibility()

        for cb in (self.chk_gamers, self.chk_creators, self.chk_accountants, self.chk_developers):
            cb.connect("toggled", lambda *_: self._update_bundle_details_visibility())

        # Update planned installation list when any option changes
        for cb in (
            self.cb_steam,
            self.cb_lutris,
            self.cb_wine,
            self.cb_mangohud,
            self.cb_gamemode,
            self.cb_gimp,
            self.cb_inkscape,
            self.cb_blender,
            self.cb_kdenlive,
            self.cb_audacity,
            self.cb_lo,
            self.cb_gnucash,
            self.cb_git,
            self.cb_base,
            self.cb_py,
            self.cb_node,
            self.cb_vscode,
        ):
            cb.connect("toggled", lambda *_: self._refresh_planned_install_label())

    def _update_bundle_details_visibility(self) -> None:
        self.gamers_box.set_visible(bool(self.chk_gamers.get_active()))
        self.creators_box.set_visible(bool(self.chk_creators.get_active()))
        self.accountants_box.set_visible(bool(self.chk_accountants.get_active()))
        self.developers_box.set_visible(bool(self.chk_developers.get_active()))

    def _update_flatpak_visibility(self) -> None:
        any_bundle = any(
            cb.get_active()
            for cb in (self.chk_gamers, self.chk_creators, self.chk_accountants, self.chk_developers)
        )
        if any_bundle:
            self.flatpak_box.hide()
        else:
            self.flatpak_box.show()

    def _refresh_selected_flatpaks_label(self) -> None:
        apps = list(self.state.config.install.flatpak_apps or [])
        if not apps:
            self.lbl_selected.set_text(self.state._("Selected Flatpaks:") + " " + self.state._("None"))
        else:
            self.lbl_selected.set_text(self.state._("Selected Flatpaks:") + " " + ", ".join(apps))

    def _refresh_planned_install_label(self) -> None:
        sel = SoftwareSelection(
            gamers=bool(self.chk_gamers.get_active()),
            creators=bool(self.chk_creators.get_active()),
            accountants=bool(self.chk_accountants.get_active()),
            developers=bool(self.chk_developers.get_active()),
            nvidia_driver=bool(self.chk_nvidia.get_active()),
            gamers_steam=bool(self.cb_steam.get_active()),
            gamers_lutris=bool(self.cb_lutris.get_active()),
            gamers_wine=bool(self.cb_wine.get_active()),
            gamers_mangohud=bool(self.cb_mangohud.get_active()),
            gamers_gamemode=bool(self.cb_gamemode.get_active()),
            creators_gimp=bool(self.cb_gimp.get_active()),
            creators_inkscape=bool(self.cb_inkscape.get_active()),
            creators_blender=bool(self.cb_blender.get_active()),
            creators_kdenlive=bool(self.cb_kdenlive.get_active()),
            creators_audacity=bool(self.cb_audacity.get_active()),
            accountants_libreoffice=bool(self.cb_lo.get_active()),
            accountants_gnucash=bool(self.cb_gnucash.get_active()),
            developers_git=bool(self.cb_git.get_active()),
            developers_base_devel=bool(self.cb_base.get_active()),
            developers_python=bool(self.cb_py.get_active()),
            developers_nodejs=bool(self.cb_node.get_active()),
            developers_vscode=bool(self.cb_vscode.get_active()),
        )

        pkgs = arch_packages_for_selection(sel)
        flatpaks = list(self.state.config.install.flatpak_apps or [])
        flatpaks += flatpak_appids_for_selection(sel)
        # Deduplicate, stable order
        seen: set[str] = set()
        flatpaks = [a for a in flatpaks if not (a in seen or seen.add(a))]

        parts: list[str] = []
        if not pkgs:
            parts.append(self.state._("System packages (pacman):") + " " + self.state._("None"))
        else:
            parts.append(self.state._("System packages (pacman):") + " " + ", ".join(pkgs))

        if not flatpaks:
            parts.append(self.state._("Flatpaks:") + " " + self.state._("None"))
        else:
            parts.append(self.state._("Flatpaks:") + " " + ", ".join(flatpaks))

        self.lbl_plan.set_text("\n".join(parts))

    def on_flatpak_search(self, _btn) -> None:
        Gtk = self.window.Gtk
        query = self.ent_flatpak.get_text().strip()
        if not query:
            return

        self.window.set_busy(True, self.state._("Searching Flatpak..."))

        def worker() -> None:
            results = search_flatpak(self.state.executor, query)

            def ui_update() -> None:
                try:
                    for row in list(self.flatpak_results.get_children()):
                        self.flatpak_results.remove(row)

                    selected = set(self.state.config.install.flatpak_apps or [])
                    for app in results:
                        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                        cb = Gtk.CheckButton(label=f"{app.name} ({app.appid})")
                        cb.set_active(app.appid in selected)
                        self._style_checkbox(cb)

                        desc = Gtk.Label(label=app.description)
                        desc.set_xalign(0)
                        desc.set_line_wrap(True)
                        row_box.pack_start(cb, False, False, 0)
                        row_box.pack_start(desc, False, False, 0)

                        lbrow = Gtk.ListBoxRow()
                        lbrow.add(row_box)
                        self.flatpak_results.add(lbrow)

                        def on_toggle(_cb, appid=app.appid):
                            apps = set(self.state.config.install.flatpak_apps or [])
                            if _cb.get_active():
                                apps.add(appid)
                            else:
                                apps.discard(appid)
                            self.state.config.install.flatpak_apps = sorted(apps)
                            self.state.config.save()
                            self._refresh_selected_flatpaks_label()
                            self._refresh_planned_install_label()

                        cb.connect("toggled", on_toggle)

                    self.flatpak_results.show_all()
                finally:
                    self.window.set_busy(False)

            self.window.GLib.idle_add(ui_update)

        Thread(target=worker, daemon=True).start()

    def on_next(self) -> None:
        cfg = self.state.config.install
        cfg.driver_nvidia = bool(self.chk_nvidia.get_active())
        cfg.profile_gamers = bool(self.chk_gamers.get_active())
        cfg.profile_creators = bool(self.chk_creators.get_active())
        cfg.profile_accountants = bool(self.chk_accountants.get_active())
        cfg.profile_developers = bool(self.chk_developers.get_active())

        cfg.gamers_steam = bool(self.cb_steam.get_active())
        cfg.gamers_lutris = bool(self.cb_lutris.get_active())
        cfg.gamers_wine = bool(self.cb_wine.get_active())
        cfg.gamers_mangohud = bool(self.cb_mangohud.get_active())
        cfg.gamers_gamemode = bool(self.cb_gamemode.get_active())

        cfg.creators_gimp = bool(self.cb_gimp.get_active())
        cfg.creators_inkscape = bool(self.cb_inkscape.get_active())
        cfg.creators_blender = bool(self.cb_blender.get_active())
        cfg.creators_kdenlive = bool(self.cb_kdenlive.get_active())
        cfg.creators_audacity = bool(self.cb_audacity.get_active())

        cfg.accountants_libreoffice = bool(self.cb_lo.get_active())
        cfg.accountants_gnucash = bool(self.cb_gnucash.get_active())

        cfg.developers_git = bool(self.cb_git.get_active())
        cfg.developers_base_devel = bool(self.cb_base.get_active())
        cfg.developers_python = bool(self.cb_py.get_active())
        cfg.developers_nodejs = bool(self.cb_node.get_active())
        cfg.developers_vscode = bool(self.cb_vscode.get_active())

        self.state.config.save()

    def sync_to_config(self) -> None:
        self.on_next()


class SummaryPage(WizardPage):
    name = "summary"

    @property
    def title(self) -> str:
        return self.state._("Summary")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.lbl = Gtk.Label()
        self.lbl.set_xalign(0)
        self.lbl.set_line_wrap(True)
        box.pack_start(self.lbl, True, True, 0)

        self.exp_fstab = Gtk.Expander(label=self.state._("fstab preview"))
        self.exp_fstab.set_expanded(False)
        sw = Gtk.ScrolledWindow()
        sw.set_hexpand(True)
        sw.set_vexpand(True)
        sw.set_size_request(-1, 140)
        self.fstab_view = Gtk.TextView()
        self.fstab_view.set_editable(False)
        self.fstab_view.set_cursor_visible(False)
        self.fstab_view.set_wrap_mode(Gtk.WrapMode.NONE)
        try:
            import gi  # type: ignore

            gi.require_version("Pango", "1.0")
            from gi.repository import Pango  # type: ignore[import-not-found]

            self.fstab_view.override_font(Pango.FontDescription("monospace"))
        except Exception:
            pass
        sw.add(self.fstab_view)
        self.exp_fstab.add(sw)
        box.pack_start(self.exp_fstab, False, False, 0)

        self.chk_confirm = Gtk.CheckButton(label=self.state._("I understand this will erase the selected disk"))
        self._style_checkbox(self.chk_confirm)
        box.pack_start(self.chk_confirm, False, False, 0)
        return box

    def on_show(self) -> None:
        cfg = self.state.config

        if cfg.install.erase_disk:
            self.chk_confirm.set_label(self.state._("I understand this will erase the selected disk"))
        else:
            self.chk_confirm.set_label(self.state._("I understand the installer will modify the selected partitions"))

        disk_lines = f"{self.state._('Disk')}: {cfg.install.target_disk}\n"
        if cfg.install.erase_disk:
            disk_lines += f"{self.state._('Erase disk')}: {cfg.install.erase_disk}\n"
        else:
            parts = [
                f"/={cfg.install.root_partition or self.state._('None')}",
                f"/boot/efi={cfg.install.efi_partition or self.state._('None')}",
                f"/home={cfg.install.home_partition or self.state._('None')}",
                f"swap={cfg.install.swap_partition or self.state._('None')}",
            ]
            disk_lines += f"{self.state._('Partitions')}: {', '.join(parts)}\n"

        self.lbl.set_text(
            self.state._("Ready to install with the following settings:")
            + "\n\n"
            + f"{self.state._('System locale')}: {cfg.install.locale}\n"
            + f"{self.state._('Keyboard layout')}: {cfg.install.keyboard_layout}\n"
            + f"{self.state._('Timezone')}: {cfg.install.timezone}\n"
            + disk_lines
            + f"{self.state._('Hostname')}: {cfg.install.hostname}\n"
            + f"{self.state._('Username')}: {cfg.install.username}\n"
            + f"{self.state._('NetworkManager')}: {cfg.install.enable_networkmanager}\n"
            + f"{self.state._('Wi-Fi SSID')}: {cfg.install.wifi_ssid or self.state._('None')}\n"
            + f"{self.state._('Bundles')}: {self._bundles_summary()}\n"
            + f"{self.state._('Dry-run')}: {cfg.runtime.dry_run}\n"
        )

        # fstab preview
        try:
            if cfg.install.erase_disk and cfg.install.target_disk:
                disk = cfg.install.target_disk
                if "nvme" in disk or "mmcblk" in disk:
                    efi_part = disk + "p1"
                    root_part = disk + "p2"
                else:
                    efi_part = disk + "1"
                    root_part = disk + "2"
                home_part = None
                swap_part = None
            else:
                root_part = cfg.install.root_partition
                efi_part = cfg.install.efi_partition or None
                home_part = cfg.install.home_partition or None
                swap_part = cfg.install.swap_partition or None

            content = build_fstab_content(
                executor=self.state.executor,
                root_part=root_part,
                efi_part=efi_part,
                home_part=home_part,
                swap_part=swap_part,
            )
        except Exception as e:
            content = self.state._("Unable to generate fstab preview:") + " " + str(e)

        buf = self.fstab_view.get_buffer()
        buf.set_text(content)
        self.chk_confirm.set_active(False)

    def _bundles_summary(self) -> str:
        cfg = self.state.config.install
        parts: list[str] = []
        if cfg.driver_nvidia:
            parts.append(self.state._("NVIDIA"))
        if cfg.profile_gamers:
            parts.append(self.state._("Gamers"))
        if cfg.profile_creators:
            parts.append(self.state._("Creators"))
        if cfg.profile_accountants:
            parts.append(self.state._("Accountants"))
        if cfg.profile_developers:
            parts.append(self.state._("Developers"))
        return ", ".join(parts) if parts else self.state._("None")

    def validate(self) -> tuple[bool, str]:
        if not self.chk_confirm.get_active():
            if self.state.config.install.erase_disk:
                return False, self.state._("Please confirm you understand the disk will be erased.")
            return False, self.state._("Please confirm you understand the selected partitions will be modified.")
        return True, ""

    def on_next(self) -> None:
        # Jump into progress page and start installation.
        pass


class ProgressPage(WizardPage):
    name = "progress"

    @property
    def title(self) -> str:
        return self.state._("Installing")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.pb = Gtk.ProgressBar()
        self.lbl = Gtk.Label()
        self.lbl.set_xalign(0)
        box.pack_start(self.lbl, False, False, 0)
        box.pack_start(self.pb, False, False, 0)
        return box

    def on_show(self) -> None:
        # Start installation in background.
        self.pb.set_fraction(0.0)
        self.lbl.set_text(self.state._("Starting...") )

        engine = InstallerEngine(
            config=self.state.config,
            executor=self.state.executor,
        )

        def progress_cb(pct: int, msg: str) -> None:
            def ui_update() -> None:
                self.pb.set_fraction(max(0.0, min(1.0, pct / 100.0)))
                self.pb.set_text(f"{pct}%")
                self.lbl.set_text(self.state._(msg))
            self.window.GLib.idle_add(ui_update)

        def worker() -> None:
            try:
                engine.run_install(progress_cb=progress_cb)
                self.window.GLib.idle_add(lambda: self.window._go_to(self.window.current_idx + 1))
            except Exception as e:
                log.exception("Install failed")
                self.state.last_error = str(e)
                self.window.GLib.idle_add(lambda: self.window._show_error(str(e)))
                self.window.GLib.idle_add(lambda: self.window._go_to(len(self.window.pages) - 1))

        Thread(target=worker, daemon=True).start()


class FinishPage(WizardPage):
    name = "finish"

    @property
    def title(self) -> str:
        return self.state._("Finished")

    def build(self):
        Gtk = self.window.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        lbl = Gtk.Label()
        lbl.set_xalign(0)
        lbl.set_line_wrap(True)

        if self.state.last_error:
            lbl.set_text(self.state._("Installation failed:") + "\n" + self.state.last_error)
        elif self.state.config.runtime.dry_run:
            lbl.set_text(self.state._("Dry-run complete. No changes were made."))
        else:
            lbl.set_text(self.state._("Installation complete. You can reboot now."))

        box.pack_start(lbl, False, False, 0)
        return box
