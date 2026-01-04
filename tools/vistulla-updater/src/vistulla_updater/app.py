from __future__ import annotations

import shutil
from dataclasses import dataclass
import re
import sys
import importlib.util
from typing import List, Optional, Tuple

import gi

if not hasattr(gi, "require_version"):
    spec = importlib.util.find_spec("gi")
    app_paths = [p for p in sys.path if p.startswith("/app/")]
    raise RuntimeError(
        "Brak PyGObject/GTK3 (albo konflikt z pakietem 'gi' z pip).\n"
        f"Python: {sys.executable}\n"
        f"Spec gi: {spec}\n"
        + (
            "Wygląda na uruchomienie w sandboxie (np. VS Code z Flatpaka) — sys.path zawiera /app/…\n"
            + "\n".join(f" - {p}" for p in app_paths)
            + "\nRozwiązanie: uruchom program w terminalu systemowym (poza Flatpakiem) albo użyj VS Code instalowanego z pacmana/AUR.\n"
            if app_paths
            else "Na Arch zainstaluj: sudo pacman -S --needed python-gobject gtk3 gobject-introspection\n"
            "i upewnij się, że nie masz zainstalowanych pipowych konfliktów: python3 -m pip uninstall -y gi pygobject PyGObject\n"
        )
    )

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, Gtk

from .commands import CommandResult, have_command, run_command_async
from .config import AppConfig, load_config, save_config
from .cinnamon import read_cinnamon_theme
from .i18n import detect_language, set_language, t


@dataclass
class FlatpakApp:
    appid: str
    name: str
    origin: str


def _parse_checkupdates_output(text: str) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("::"):
            continue
        # expected: pkg oldver -> newver
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "->":
            rows.append((parts[0], parts[1], parts[3]))
        else:
            # fallback: store whole line
            rows.append((line, "", ""))
    return rows


def _parse_flatpak_info_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip().lower()
        val = v.strip()
        if not key:
            continue
        out[key] = val
    return out


def _split_columns(line: str, *, min_cols: int) -> List[str]:
    # Flatpak sometimes uses tabs, sometimes aligned spaces.
    parts = [p.strip() for p in line.split("\t") if p.strip()]
    if len(parts) >= min_cols:
        return parts
    parts = [p.strip() for p in re.split(r"\s{2,}", line.strip()) if p.strip()]
    if len(parts) >= min_cols:
        return parts
    parts = [p.strip() for p in line.split() if p.strip()]
    return parts


class VistullaUpdaterWindow(Gtk.Window):
    def __init__(self) -> None:
        self.cfg: AppConfig = load_config()
        if self.cfg.language:
            set_language(self.cfg.language)
        else:
            set_language(detect_language())

        super().__init__(title=t("app.title"))
        self.set_default_size(980, 640)

        # Modern window chrome (respects Cinnamon theme)
        self.headerbar = Gtk.HeaderBar()
        self.headerbar.set_show_close_button(True)
        self.headerbar.set_title(t("app.title"))
        self.set_titlebar(self.headerbar)

        self._apply_cinnamon_theme()

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_border_width(10)
        self.add(outer)

        self.notebook = Gtk.Notebook()
        outer.pack_start(self.notebook, True, True, 0)

        sys_tab = self._build_system_tab()
        flatpak_tab = self._build_flatpak_tab()
        settings_tab = self._build_settings_tab()

        self.tab_label_system = Gtk.Label(label=t("tab.system"))
        self.tab_label_flatpak = Gtk.Label(label=t("tab.flatpak"))
        self.tab_label_settings = Gtk.Label(label=t("tab.settings"))

        for lbl in (self.tab_label_system, self.tab_label_flatpak, self.tab_label_settings):
            lbl.set_margin_start(10)
            lbl.set_margin_end(10)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)

        self.notebook.append_page(sys_tab, self.tab_label_system)
        self.notebook.append_page(flatpak_tab, self.tab_label_flatpak)
        self.notebook.append_page(settings_tab, self.tab_label_settings)

        # Auto-refresh on tab changes
        self.notebook.connect("switch-page", self.on_main_switch_page)
        self.fp_notebook.connect("switch-page", self.on_fp_switch_page)

        self._set_initial_status()
        self._apply_translations()

        # Initial loads (only if flatpak exists)
        if have_command("flatpak"):
            self.on_fp_refresh_remotes(self.btn_fp_refresh_remotes)

            # NOTE: Store refresh is triggered after remotes are loaded/synced.
            # Calling it here may use a stale cfg.store_remote (e.g. "$" from old logs).

    def _apply_cinnamon_theme(self) -> None:
        try:
            theme = read_cinnamon_theme()
        except Exception:
            return
        settings = Gtk.Settings.get_default()
        if settings is None:
            return
        if theme.gtk_theme:
            settings.set_property("gtk-theme-name", theme.gtk_theme)
        if theme.icon_theme:
            settings.set_property("gtk-icon-theme-name", theme.icon_theme)

    def _apply_translations(self) -> None:
        self.set_title(t("app.title"))

        if hasattr(self, "headerbar") and self.headerbar is not None:
            self.headerbar.set_title(t("app.title"))

        self.tab_label_system.set_text(t("tab.system"))
        self.tab_label_flatpak.set_text(t("tab.flatpak"))
        self.tab_label_settings.set_text(t("tab.settings"))

        # System
        self.btn_sys_check.set_label(t("sys.check"))
        self.btn_sys_update.set_label(t("sys.update"))
        self.sys_col_pkg.set_title(t("sys.col.pkg"))
        self.sys_col_cur.set_title(t("sys.col.cur"))
        self.sys_col_new.set_title(t("sys.col.new"))

        # Flatpak: store
        self.lbl_fp_store_remote.set_text(t("fp.store.remote"))
        self.btn_fp_store_refresh.set_label(t("fp.store.refresh"))
        self.lbl_fp_store_categories.set_text(t("fp.store.categories"))
        self.flatpak_query.set_placeholder_text(t("fp.store.filter"))
        self.btn_fp_search.set_label(t("fp.search"))
        self.btn_fp_install.set_label(t("fp.install"))
        self.btn_fp_uninstall.set_label(t("fp.uninstall"))
        self.btn_fp_update.set_label(t("fp.update_all"))
        self.fp_col_appid.set_title(t("fp.col.appid"))
        self.fp_col_name.set_title(t("fp.col.name"))
        self.fp_col_origin.set_title(t("fp.col.origin"))

        # Flatpak: details
        self.fp_details_frame.set_label(t("fp.details.title"))
        self.fp_details_lbl_appid.set_text(t("fp.details.appid"))
        self.fp_details_lbl_name.set_text(t("fp.details.name"))
        self.fp_details_lbl_origin.set_text(t("fp.details.origin"))
        self.fp_details_lbl_version.set_text(t("fp.details.version"))
        self.fp_details_lbl_branch.set_text(t("fp.details.branch"))
        self.fp_details_lbl_license.set_text(t("fp.details.license"))
        self.fp_details_lbl_author.set_text(t("fp.details.author"))
        self.fp_details_lbl_size.set_text(t("fp.details.size"))
        self.fp_details_lbl_description.set_text(t("fp.details.description"))

        # Flatpak: installed
        self.btn_fp_refresh_installed.set_label(t("fp.refresh_installed"))
        self.btn_fp_installed_uninstall.set_label(t("fp.uninstall"))
        self.fp_inst_col_appid.set_title(t("fp.col.appid"))
        self.fp_inst_col_name.set_title(t("fp.col.name"))
        self.fp_inst_col_origin.set_title(t("fp.col.origin"))

        # Flatpak: remotes
        self.btn_fp_refresh_remotes.set_label(t("fp.refresh_remotes"))
        self.btn_fp_add_remote.set_label(t("fp.add_remote"))
        self.btn_fp_set_default_remote.set_label(t("fp.set_default_remote"))
        self.lbl_fp_remote_apps.set_text(t("fp.remote.apps"))
        self.btn_fp_remote_uninstall.set_label(t("fp.remote.uninstall_app"))
        self.fp_remote_col_name.set_title(t("fp.col.remote"))
        self.fp_remote_col_url.set_title(t("fp.col.url"))
        self.fp_remote_col_default.set_title(t("fp.col.default"))

        # Settings
        self.lbl_settings_language.set_text(t("settings.language"))
        self.lbl_settings_theme.set_text(t("settings.theme"))
        self.lbl_settings_theme_value.set_text(t("settings.theme.auto"))

    # -------------------- System tab --------------------

    def _build_system_tab(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(row, False, False, 0)

        self.btn_sys_check = Gtk.Button(label=t("sys.check"))
        self.btn_sys_check.connect("clicked", self.on_sys_check)
        row.pack_start(self.btn_sys_check, False, False, 0)

        self.btn_sys_update = Gtk.Button(label=t("sys.update"))
        self.btn_sys_update.connect("clicked", self.on_sys_update)
        row.pack_start(self.btn_sys_update, False, False, 0)

        self.sys_store = Gtk.ListStore(str, str, str)
        tree = Gtk.TreeView(model=self.sys_store)
        renderer = Gtk.CellRendererText()
        self.sys_col_pkg = Gtk.TreeViewColumn(t("sys.col.pkg"), renderer, text=0)
        self.sys_col_cur = Gtk.TreeViewColumn(t("sys.col.cur"), renderer, text=1)
        self.sys_col_new = Gtk.TreeViewColumn(t("sys.col.new"), renderer, text=2)
        for col in (self.sys_col_pkg, self.sys_col_cur, self.sys_col_new):
            col.set_resizable(True)
            tree.append_column(col)

        list_frame = Gtk.Frame()
        list_frame.set_shadow_type(Gtk.ShadowType.IN)
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.add(tree)
        list_frame.add(scroller)
        root.pack_start(list_frame, True, True, 0)

        self.sys_log_buf = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.sys_log_buf)
        log_view.set_editable(False)
        log_view.set_monospace(True)
        log_frame = Gtk.Frame()
        log_frame.set_shadow_type(Gtk.ShadowType.IN)
        log_scroller = Gtk.ScrolledWindow()
        log_scroller.set_vexpand(False)
        log_scroller.set_size_request(-1, 220)
        log_scroller.add(log_view)
        log_frame.add(log_scroller)
        root.pack_start(log_frame, False, False, 0)

        self.sys_status = Gtk.Label(label="")
        self.sys_status.set_xalign(0)
        root.pack_start(self.sys_status, False, False, 0)

        return root

    def _append_sys_log(self, text: str) -> None:
        end = self.sys_log_buf.get_end_iter()
        self.sys_log_buf.insert(end, text)

    def _set_sys_status(self, text: str) -> None:
        self.sys_status.set_text(text)

    def on_sys_check(self, _btn: Gtk.Button) -> None:
        self.sys_store.clear()
        self.sys_log_buf.set_text("")

        if have_command("checkupdates"):
            argv = ["checkupdates"]
        else:
            argv = ["pacman", "-Qu"]

        self._set_sys_status(t("sys.status.checking"))

        collected: List[str] = []

        def on_line(line: str) -> None:
            collected.append(line)
            self._append_sys_log(line)

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0 and res.exit_code != 2:
                self._set_sys_status(t("sys.status.check_error"))
                return
            rows = _parse_checkupdates_output("".join(collected))
            for pkg, cur, new in rows:
                self.sys_store.append([pkg, cur, new])
            self._set_sys_status(t("sys.status.found", n=len(rows)))

        run_command_async(argv, on_line=on_line, on_done=on_done)

    def on_sys_update(self, _btn: Gtk.Button) -> None:
        self._append_sys_log(f"\n{t('sys.log.update_header')}\n")
        self._set_sys_status(t("sys.status.updating"))

        if not have_command("pacman"):
            self._append_sys_log(t("sys.err.no_pacman") + "\n")
            self._set_sys_status(t("sys.status.no_pacman"))
            return

        argv = ["pacman", "-Syu", "--noconfirm"]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_sys_status(t("sys.status.updated"))
            else:
                self._set_sys_status(t("sys.status.update_failed"))

        run_command_async(argv, use_pkexec=True, on_line=self._append_sys_log, on_done=on_done)

    # -------------------- Flatpak tab --------------------

    def _build_flatpak_tab(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        self.fp_notebook = Gtk.Notebook()
        root.pack_start(self.fp_notebook, True, True, 0)

        store_tab = self._build_flatpak_store_tab()
        installed_tab = self._build_flatpak_installed_tab()
        remotes_tab = self._build_flatpak_remotes_tab()

        self.fp_label_store = Gtk.Label(label=t("fp.subtab.store"))
        self.fp_label_installed = Gtk.Label(label=t("fp.subtab.installed"))
        self.fp_label_remotes = Gtk.Label(label=t("fp.subtab.remotes"))

        for lbl in (self.fp_label_store, self.fp_label_installed, self.fp_label_remotes):
            lbl.set_margin_start(10)
            lbl.set_margin_end(10)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)

        self.fp_notebook.append_page(store_tab, self.fp_label_store)
        self.fp_notebook.append_page(installed_tab, self.fp_label_installed)
        self.fp_notebook.append_page(remotes_tab, self.fp_label_remotes)

        return root

    def _build_flatpak_store_tab(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        top_frame = Gtk.Frame()
        top_frame.set_shadow_type(Gtk.ShadowType.IN)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.set_border_width(8)
        top_frame.add(top)
        root.pack_start(top_frame, False, False, 0)

        self.lbl_fp_store_remote = Gtk.Label(label=t("fp.store.remote"))
        self.lbl_fp_store_remote.set_xalign(0)
        top.pack_start(self.lbl_fp_store_remote, False, False, 0)

        self.combo_fp_store_remote = Gtk.ComboBoxText()
        self.combo_fp_store_remote.connect("changed", self.on_fp_store_remote_changed)
        top.pack_start(self.combo_fp_store_remote, False, False, 0)

        self.btn_fp_store_refresh = Gtk.Button(label=t("fp.store.refresh"))
        self.btn_fp_store_refresh.connect("clicked", self.on_fp_store_refresh)
        top.pack_start(self.btn_fp_store_refresh, False, False, 0)

        row_frame = Gtk.Frame()
        row_frame.set_shadow_type(Gtk.ShadowType.IN)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_border_width(8)
        row_frame.add(row)
        root.pack_start(row_frame, False, False, 0)

        self.flatpak_query = Gtk.Entry()
        self.flatpak_query.set_placeholder_text(t("fp.store.filter"))
        self.flatpak_query.connect("changed", self.on_fp_store_filter_changed)
        row.pack_start(self.flatpak_query, True, True, 0)

        self.btn_fp_search = Gtk.Button(label=t("fp.search"))
        self.btn_fp_search.connect("clicked", self.on_fp_store_apply_filters)
        row.pack_start(self.btn_fp_search, False, False, 0)

        # Actions are available in the details panel; hide duplicates to reduce clutter.
        self.btn_fp_install = Gtk.Button(label=t("fp.install"))
        self.btn_fp_install.connect("clicked", self.on_fp_install)
        self.btn_fp_install.set_no_show_all(True)
        self.btn_fp_install.hide()

        self.btn_fp_uninstall = Gtk.Button(label=t("fp.uninstall"))
        self.btn_fp_uninstall.connect("clicked", self.on_fp_uninstall)
        self.btn_fp_uninstall.set_no_show_all(True)
        self.btn_fp_uninstall.hide()

        self.btn_fp_update = Gtk.Button(label=t("fp.update_all"))
        self.btn_fp_update.connect("clicked", self.on_fp_update_all)
        row.pack_start(self.btn_fp_update, False, False, 0)

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        pane.set_wide_handle(True)
        root.pack_start(pane, True, True, 0)

        # Categories
        left_frame = Gtk.Frame()
        left_frame.set_shadow_type(Gtk.ShadowType.IN)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_border_width(8)
        self.lbl_fp_store_categories = Gtk.Label(label=t("fp.store.categories"))
        self.lbl_fp_store_categories.set_xalign(0)
        left.pack_start(self.lbl_fp_store_categories, False, False, 0)

        self.fp_cat_store = Gtk.ListStore(str)
        self.fp_cat_tree = Gtk.TreeView(model=self.fp_cat_store)
        self.fp_cat_tree.set_headers_visible(False)
        cat_renderer = Gtk.CellRendererText()
        cat_col = Gtk.TreeViewColumn(t("fp.store.categories"), cat_renderer, text=0)
        cat_col.set_resizable(True)
        self.fp_cat_tree.append_column(cat_col)
        self.fp_cat_tree.get_selection().connect("changed", self.on_fp_category_changed)

        left_scroller = Gtk.ScrolledWindow()
        left_scroller.set_vexpand(True)
        left_scroller.add(self.fp_cat_tree)
        left.pack_start(left_scroller, True, True, 0)

        left_frame.add(left)
        pane.add1(left_frame)

        # App list
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        app_list_frame = Gtk.Frame()
        app_list_frame.set_shadow_type(Gtk.ShadowType.IN)
        app_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        app_list_box.set_border_width(8)

        self.fp_store = Gtk.ListStore(str, str, str)
        self.fp_tree = Gtk.TreeView(model=self.fp_store)
        self.fp_tree.get_selection().connect("changed", self.on_fp_store_selection_changed)
        fp_renderer = Gtk.CellRendererText()
        self.fp_col_appid = Gtk.TreeViewColumn(t("fp.col.appid"), fp_renderer, text=0)
        self.fp_col_name = Gtk.TreeViewColumn(t("fp.col.name"), fp_renderer, text=1)
        self.fp_col_origin = Gtk.TreeViewColumn(t("fp.col.origin"), fp_renderer, text=2)
        for col in (self.fp_col_appid, self.fp_col_name, self.fp_col_origin):
            col.set_resizable(True)
            self.fp_tree.append_column(col)

        fp_scroller = Gtk.ScrolledWindow()
        fp_scroller.set_vexpand(True)
        fp_scroller.add(self.fp_tree)
        app_list_box.pack_start(fp_scroller, True, True, 0)
        app_list_frame.add(app_list_box)
        right.pack_start(app_list_frame, True, True, 0)

        # Details panel
        self.fp_details_frame = Gtk.Frame(label=t("fp.details.title"))
        self.fp_details_frame.set_shadow_type(Gtk.ShadowType.IN)
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        details_box.set_border_width(8)
        self.fp_details_frame.add(details_box)

        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(10)
        details_box.pack_start(grid, False, False, 0)

        def mk_label(txt: str) -> Gtk.Label:
            lbl = Gtk.Label(label=txt)
            lbl.set_xalign(0)
            return lbl

        self.fp_details_lbl_appid = mk_label(t("fp.details.appid"))
        self.fp_details_lbl_name = mk_label(t("fp.details.name"))
        self.fp_details_lbl_origin = mk_label(t("fp.details.origin"))
        self.fp_details_lbl_version = mk_label(t("fp.details.version"))
        self.fp_details_lbl_branch = mk_label(t("fp.details.branch"))
        self.fp_details_lbl_license = mk_label(t("fp.details.license"))
        self.fp_details_lbl_author = mk_label(t("fp.details.author"))
        self.fp_details_lbl_size = mk_label(t("fp.details.size"))
        self.fp_details_lbl_description = mk_label(t("fp.details.description"))

        self.fp_details_val_appid = mk_label("")
        self.fp_details_val_name = mk_label("")
        self.fp_details_val_origin = mk_label("")
        self.fp_details_val_version = mk_label("")
        self.fp_details_val_branch = mk_label("")
        self.fp_details_val_license = mk_label("")
        self.fp_details_val_author = mk_label("")
        self.fp_details_val_size = mk_label("")

        grid.attach(self.fp_details_lbl_appid, 0, 0, 1, 1)
        grid.attach(self.fp_details_val_appid, 1, 0, 1, 1)
        grid.attach(self.fp_details_lbl_name, 0, 1, 1, 1)
        grid.attach(self.fp_details_val_name, 1, 1, 1, 1)
        grid.attach(self.fp_details_lbl_origin, 0, 2, 1, 1)
        grid.attach(self.fp_details_val_origin, 1, 2, 1, 1)
        grid.attach(self.fp_details_lbl_version, 0, 3, 1, 1)
        grid.attach(self.fp_details_val_version, 1, 3, 1, 1)
        grid.attach(self.fp_details_lbl_branch, 0, 4, 1, 1)
        grid.attach(self.fp_details_val_branch, 1, 4, 1, 1)
        grid.attach(self.fp_details_lbl_license, 0, 5, 1, 1)
        grid.attach(self.fp_details_val_license, 1, 5, 1, 1)
        grid.attach(self.fp_details_lbl_author, 0, 6, 1, 1)
        grid.attach(self.fp_details_val_author, 1, 6, 1, 1)
        grid.attach(self.fp_details_lbl_size, 0, 7, 1, 1)
        grid.attach(self.fp_details_val_size, 1, 7, 1, 1)

        grid.attach(self.fp_details_lbl_description, 0, 8, 1, 1)
        self.fp_details_desc_buf = Gtk.TextBuffer()
        self.fp_details_desc_view = Gtk.TextView(buffer=self.fp_details_desc_buf)
        self.fp_details_desc_view.set_editable(False)
        self.fp_details_desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        desc_scroller = Gtk.ScrolledWindow()
        desc_scroller.set_vexpand(True)
        desc_scroller.set_size_request(-1, 120)
        desc_scroller.add(self.fp_details_desc_view)
        grid.attach(desc_scroller, 1, 8, 1, 1)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        details_box.pack_start(btn_row, False, False, 0)
        self.btn_fp_details_install = Gtk.Button(label=t("fp.install"))
        self.btn_fp_details_install.connect("clicked", self.on_fp_install)
        btn_row.pack_start(self.btn_fp_details_install, False, False, 0)

        self.btn_fp_details_uninstall = Gtk.Button(label=t("fp.uninstall"))
        self.btn_fp_details_uninstall.connect("clicked", self.on_fp_uninstall)
        btn_row.pack_start(self.btn_fp_details_uninstall, False, False, 0)

        right.pack_start(self.fp_details_frame, False, False, 0)

        pane.add2(right)

        self.fp_log_buf = Gtk.TextBuffer()
        fp_log_view = Gtk.TextView(buffer=self.fp_log_buf)
        fp_log_view.set_editable(False)
        fp_log_view.set_monospace(True)
        fp_log_frame = Gtk.Frame()
        fp_log_frame.set_shadow_type(Gtk.ShadowType.IN)
        fp_log_scroller = Gtk.ScrolledWindow()
        fp_log_scroller.set_vexpand(False)
        fp_log_scroller.set_size_request(-1, 180)
        fp_log_scroller.add(fp_log_view)
        fp_log_frame.add(fp_log_scroller)
        root.pack_start(fp_log_frame, False, False, 0)

        self.fp_status = Gtk.Label(label="")
        self.fp_status.set_xalign(0)
        root.pack_start(self.fp_status, False, False, 0)

        self._store_all_apps: List[FlatpakApp] = []
        self._details_last_appid: str = ""
        self._populate_categories()

        return root

    def on_main_switch_page(self, _nb: Gtk.Notebook, _page: Gtk.Widget, page_num: int) -> None:
        # 0=System, 1=Flatpak, 2=Settings
        if page_num != 1:
            return
        if not have_command("flatpak"):
            return
        self.on_fp_refresh_remotes(self.btn_fp_refresh_remotes)
        self.on_fp_switch_page(self.fp_notebook, self.fp_notebook.get_nth_page(self.fp_notebook.get_current_page()), self.fp_notebook.get_current_page())

    def on_fp_switch_page(self, _nb: Gtk.Notebook, _page: Gtk.Widget, page_num: int) -> None:
        if not have_command("flatpak"):
            return
        # 0=Store, 1=Installed, 2=Remotes
        if page_num == 0:
            self.on_fp_store_refresh(self.btn_fp_store_refresh)
        elif page_num == 1:
            self.on_fp_refresh_installed(self.btn_fp_refresh_installed)
        elif page_num == 2:
            self.on_fp_refresh_remotes(self.btn_fp_refresh_remotes)
            self.on_fp_remote_refresh_apps()

    def on_fp_store_selection_changed(self, _sel) -> None:
        app = self._selected_flatpak_app()
        if app is None:
            return
        if app.appid == self._details_last_appid:
            return
        self._details_last_appid = app.appid
        self._load_flatpak_app_details(app)

    def _set_details_values(
        self,
        *,
        appid: str = "",
        name: str = "",
        origin: str = "",
        version: str = "",
        branch: str = "",
        license: str = "",
        author: str = "",
        size: str = "",
        description: str = "",
    ) -> None:
        self.fp_details_val_appid.set_text(appid)
        self.fp_details_val_name.set_text(name)
        self.fp_details_val_origin.set_text(origin)
        self.fp_details_val_version.set_text(version)
        self.fp_details_val_branch.set_text(branch)
        self.fp_details_val_license.set_text(license)
        self.fp_details_val_author.set_text(author)
        self.fp_details_val_size.set_text(size)
        self.fp_details_desc_buf.set_text(description)

    def _load_flatpak_app_details(self, app: FlatpakApp) -> None:
        self._set_fp_status(t("fp.details.loading"))
        self._set_details_values(appid=app.appid, name=app.name, origin=app.origin)

        # check installed status to toggle buttons
        def set_buttons(installed: bool) -> None:
            self.btn_fp_details_install.set_sensitive(not installed)
            self.btn_fp_details_uninstall.set_sensitive(installed)

        # fast check: flatpak info appid
        run_command_async(
            ["flatpak", "info", app.appid],
            on_done=lambda res: set_buttons(res.exit_code == 0),
        )

        collected: List[str] = []
        if app.origin:
            argv = ["flatpak", "remote-info", app.origin, app.appid]
        else:
            argv = ["flatpak", "info", app.appid]

        def on_line(line: str) -> None:
            collected.append(line)

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0:
                self._set_fp_status(t("fp.details.load_failed"))
                return

            text = "".join(collected)
            kv = _parse_flatpak_info_kv(text)

            # Keys vary slightly; try a few common variants
            name = kv.get("name", app.name)
            version = kv.get("version", "")
            branch = kv.get("branch", "")
            license = kv.get("license", "")
            author = kv.get("author", kv.get("developer", ""))
            size = kv.get("installed size", kv.get("download size", ""))

            # Description may be a dedicated key, or multi-line; best-effort
            description = kv.get("description", "")
            if not description:
                # Try to capture lines after 'Description:'
                lines = text.splitlines()
                desc_lines: List[str] = []
                in_desc = False
                for ln in lines:
                    if in_desc:
                        if ln.strip() == "":
                            if desc_lines:
                                break
                            continue
                        desc_lines.append(ln.strip())
                        continue
                    if ln.lower().startswith("description:"):
                        maybe = ln.split(":", 1)[1].strip()
                        if maybe:
                            desc_lines.append(maybe)
                        in_desc = True
                description = "\n".join(desc_lines)

            self._set_details_values(
                appid=app.appid,
                name=name,
                origin=app.origin,
                version=version,
                branch=branch,
                license=license,
                author=author,
                size=size,
                description=description,
            )
            self._set_fp_status(t("fp.status.results", n=len(self.fp_store)))

        run_command_async(argv, on_line=on_line, on_done=on_done)

    def _build_flatpak_installed_tab(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(row, False, False, 0)

        self.btn_fp_refresh_installed = Gtk.Button(label=t("fp.refresh_installed"))
        self.btn_fp_refresh_installed.connect("clicked", self.on_fp_refresh_installed)
        row.pack_start(self.btn_fp_refresh_installed, False, False, 0)

        self.btn_fp_installed_uninstall = Gtk.Button(label=t("fp.uninstall"))
        self.btn_fp_installed_uninstall.connect("clicked", self.on_fp_uninstall_installed)
        row.pack_start(self.btn_fp_installed_uninstall, False, False, 0)

        self.fp_inst_store = Gtk.ListStore(str, str, str)
        self.fp_inst_tree = Gtk.TreeView(model=self.fp_inst_store)
        inst_renderer = Gtk.CellRendererText()
        self.fp_inst_col_appid = Gtk.TreeViewColumn(t("fp.col.appid"), inst_renderer, text=0)
        self.fp_inst_col_name = Gtk.TreeViewColumn(t("fp.col.name"), inst_renderer, text=1)
        self.fp_inst_col_origin = Gtk.TreeViewColumn(t("fp.col.origin"), inst_renderer, text=2)
        for col in (self.fp_inst_col_appid, self.fp_inst_col_name, self.fp_inst_col_origin):
            col.set_resizable(True)
            self.fp_inst_tree.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.add(self.fp_inst_tree)
        root.pack_start(scroller, True, True, 0)

        return root

    def _selected_installed_app(self) -> Optional[FlatpakApp]:
        sel = self.fp_inst_tree.get_selection()
        model, itr = sel.get_selected()
        if model is None or itr is None:
            return None
        return FlatpakApp(
            appid=str(model.get_value(itr, 0)),
            name=str(model.get_value(itr, 1)),
            origin=str(model.get_value(itr, 2)),
        )

    def on_fp_uninstall_installed(self, _btn: Gtk.Button) -> None:
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
            return

        app = self._selected_installed_app()
        if app is None:
            self._set_fp_status(t("fp.status.no_selection"))
            return

        self._append_fp_log(f"\n--- Odinstalowanie {app.appid} ---\n")
        self._set_fp_status(t("fp.status.uninstalling"))

        argv = ["flatpak", "uninstall", "-y", app.appid]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_fp_status(t("fp.status.uninstalled"))
                self.on_fp_refresh_installed(self.btn_fp_refresh_installed)
                # keep remote view in sync if user is there
                try:
                    if self.fp_notebook.get_current_page() == 2:
                        self.on_fp_remote_refresh_apps()
                except Exception:
                    pass
            else:
                self._set_fp_status(t("fp.status.uninstall_failed"))

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    def _build_flatpak_remotes_tab(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(row, False, False, 0)

        self.btn_fp_refresh_remotes = Gtk.Button(label=t("fp.refresh_remotes"))
        self.btn_fp_refresh_remotes.connect("clicked", self.on_fp_refresh_remotes)
        row.pack_start(self.btn_fp_refresh_remotes, False, False, 0)

        self.btn_fp_add_remote = Gtk.Button(label=t("fp.add_remote"))
        self.btn_fp_add_remote.connect("clicked", self.on_fp_add_remote)
        row.pack_start(self.btn_fp_add_remote, False, False, 0)

        self.btn_fp_set_default_remote = Gtk.Button(label=t("fp.set_default_remote"))
        self.btn_fp_set_default_remote.connect("clicked", self.on_fp_set_default_remote)
        row.pack_start(self.btn_fp_set_default_remote, False, False, 0)

        # name, url, default
        self.fp_remote_store = Gtk.ListStore(str, str, bool)
        self.fp_remote_tree = Gtk.TreeView(model=self.fp_remote_store)
        self.fp_remote_tree.get_selection().connect("changed", self.on_fp_remote_selection_changed)

        name_renderer = Gtk.CellRendererText()
        self.fp_remote_col_name = Gtk.TreeViewColumn(t("fp.col.remote"), name_renderer, text=0)
        url_renderer = Gtk.CellRendererText()
        self.fp_remote_col_url = Gtk.TreeViewColumn(t("fp.col.url"), url_renderer, text=1)
        default_renderer = Gtk.CellRendererToggle()
        default_renderer.set_sensitive(False)
        self.fp_remote_col_default = Gtk.TreeViewColumn(t("fp.col.default"), default_renderer, active=2)

        for col in (self.fp_remote_col_name, self.fp_remote_col_url, self.fp_remote_col_default):
            col.set_resizable(True)
            self.fp_remote_tree.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.add(self.fp_remote_tree)
        root.pack_start(scroller, True, True, 0)

        # Remote apps
        remote_apps_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.lbl_fp_remote_apps = Gtk.Label(label=t("fp.remote.apps"))
        self.lbl_fp_remote_apps.set_xalign(0)
        remote_apps_header.pack_start(self.lbl_fp_remote_apps, True, True, 0)

        self.btn_fp_remote_uninstall = Gtk.Button(label=t("fp.remote.uninstall_app"))
        self.btn_fp_remote_uninstall.connect("clicked", self.on_fp_remote_uninstall_app)
        remote_apps_header.pack_start(self.btn_fp_remote_uninstall, False, False, 0)
        root.pack_start(remote_apps_header, False, False, 0)

        self.fp_remote_apps_store = Gtk.ListStore(str, str, str)
        self.fp_remote_apps_tree = Gtk.TreeView(model=self.fp_remote_apps_store)
        ra_renderer = Gtk.CellRendererText()
        ra_col_appid = Gtk.TreeViewColumn(t("fp.col.appid"), ra_renderer, text=0)
        ra_col_name = Gtk.TreeViewColumn(t("fp.col.name"), ra_renderer, text=1)
        ra_col_origin = Gtk.TreeViewColumn(t("fp.col.origin"), ra_renderer, text=2)
        for col in (ra_col_appid, ra_col_name, ra_col_origin):
            col.set_resizable(True)
            self.fp_remote_apps_tree.append_column(col)

        ra_scroller = Gtk.ScrolledWindow()
        ra_scroller.set_vexpand(True)
        ra_scroller.set_size_request(-1, 200)
        ra_scroller.add(self.fp_remote_apps_tree)
        root.pack_start(ra_scroller, True, True, 0)

        return root

    def _build_settings_tab(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(12)
        root.pack_start(grid, False, False, 0)

        self.lbl_settings_language = Gtk.Label(label=t("settings.language"))
        self.lbl_settings_language.set_xalign(0)
        grid.attach(self.lbl_settings_language, 0, 0, 1, 1)

        self.combo_language = Gtk.ComboBoxText()
        self.combo_language.append("pl", "Polski")
        self.combo_language.append("en", "English")
        self.combo_language.set_active_id(self.cfg.language if self.cfg.language in ("pl", "en") else detect_language())
        self.combo_language.connect("changed", self.on_language_changed)
        grid.attach(self.combo_language, 1, 0, 1, 1)

        self.lbl_settings_theme = Gtk.Label(label=t("settings.theme"))
        self.lbl_settings_theme.set_xalign(0)
        grid.attach(self.lbl_settings_theme, 0, 1, 1, 1)

        self.lbl_settings_theme_value = Gtk.Label(label=t("settings.theme.auto"))
        self.lbl_settings_theme_value.set_xalign(0)
        grid.attach(self.lbl_settings_theme_value, 1, 1, 1, 1)

        return root

    def _append_fp_log(self, text: str) -> None:
        end = self.fp_log_buf.get_end_iter()
        self.fp_log_buf.insert(end, text)

    def _set_fp_status(self, text: str) -> None:
        self.fp_status.set_text(text)

    def _selected_flatpak_app(self) -> Optional[FlatpakApp]:
        sel = self.fp_tree.get_selection()
        model, itr = sel.get_selected()
        if model is None or itr is None:
            return None
        appid = str(model.get_value(itr, 0))
        name = str(model.get_value(itr, 1))
        origin = str(model.get_value(itr, 2))
        return FlatpakApp(appid=appid, name=name, origin=origin)

    def on_fp_search(self, _btn: Gtk.Button) -> None:
        self.fp_store.clear()
        self.fp_log_buf.set_text("")

        if not have_command("flatpak"):
            self._append_fp_log(t("fp.status.no_flatpak") + "\n")
            self._set_fp_status(t("fp.status.no_flatpak"))
            return

        query = self.flatpak_query.get_text().strip()
        if not query:
            self._set_fp_status(t("fp.status.type_query"))
            return

        self._set_fp_status(t("fp.status.searching"))

        collected: List[str] = []
        argv = [
            "flatpak",
            "search",
            query,
            "--columns=application,name,origin",
        ]

        def on_line(line: str) -> None:
            collected.append(line)
            self._append_fp_log(line)

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0:
                self._set_fp_status(t("fp.status.search_error"))
                return

            # flatpak search prints a header line; we parse tab-separated columns
            apps: List[FlatpakApp] = []
            for raw in "".join(collected).splitlines():
                line = raw.strip()
                if not line or line.lower().startswith("application"):
                    continue
                parts = [p.strip() for p in line.split("\t")]
                if len(parts) >= 3:
                    apps.append(FlatpakApp(appid=parts[0], name=parts[1], origin=parts[2]))

            for app in apps:
                self.fp_store.append([app.appid, app.name, app.origin])

            self._set_fp_status(t("fp.status.results", n=len(apps)))

        run_command_async(argv, on_line=on_line, on_done=on_done)

    # -------------------- Store (remote + categories) --------------------

    def _populate_categories(self) -> None:
        self.fp_cat_store.clear()
        self.fp_cat_store.append([t("fp.store.category.all")])
        for name in sorted(self.cfg.categories.keys()):
            self.fp_cat_store.append([name])
        # select first
        sel = self.fp_cat_tree.get_selection()
        model = self.fp_cat_tree.get_model()
        if model is not None and len(model) > 0:
            sel.select_path(0)

    def _selected_category(self) -> str:
        sel = self.fp_cat_tree.get_selection()
        model, itr = sel.get_selected()
        if model is None or itr is None:
            return t("fp.store.category.all")
        return str(model.get_value(itr, 0))

    def on_fp_category_changed(self, _sel) -> None:
        self.on_fp_store_apply_filters(self.btn_fp_search)

    def on_fp_store_filter_changed(self, _entry: Gtk.Entry) -> None:
        self.on_fp_store_apply_filters(self.btn_fp_search)

    def on_fp_store_apply_filters(self, _btn: Gtk.Button) -> None:
        category = self._selected_category()
        query = self.flatpak_query.get_text().strip().lower()

        if category == t("fp.store.category.all"):
            allowed = None
        else:
            allowed = set(self.cfg.categories.get(category, []))

        filtered: List[FlatpakApp] = []
        for app in self._store_all_apps:
            if allowed is not None and app.appid not in allowed:
                continue
            if query and (query not in app.appid.lower()) and (query not in app.name.lower()):
                continue
            filtered.append(app)

        self.fp_store.clear()
        for app in filtered:
            self.fp_store.append([app.appid, app.name, app.origin])
        self._set_fp_status(t("fp.status.results", n=len(filtered)))

    def on_fp_store_remote_changed(self, _combo: Gtk.ComboBoxText) -> None:
        active = self.combo_fp_store_remote.get_active_id() or ""
        self.cfg.store_remote = active
        save_config(self.cfg)
        self.on_fp_store_refresh(self.btn_fp_store_refresh)

    def _store_active_remote(self) -> str:
        rid = self.combo_fp_store_remote.get_active_id()
        if rid:
            return rid
        if self.cfg.store_remote:
            # Avoid accidental log-prefix remote name
            if self.cfg.store_remote != "$" and not any(ch.isspace() for ch in self.cfg.store_remote):
                return self.cfg.store_remote
        return ""

    def on_fp_store_refresh(self, _btn: Gtk.Button) -> None:
        self.fp_log_buf.set_text("")
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
            return

        remote = self._store_active_remote()
        if not remote:
            self._set_fp_status(t("fp.status.no_remote"))
            return

        self._set_fp_status(t("fp.status.loading_store"))
        collected: List[str] = []
        argv = ["flatpak", "remote-ls", remote, "--app", "--columns=application,name"]

        def on_line(line: str) -> None:
            collected.append(line)
            self._append_fp_log(line)

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0:
                self._set_fp_status(t("fp.status.search_error"))
                return

            apps: List[FlatpakApp] = []
            for raw in "".join(collected).splitlines():
                line = raw.strip()
                if not line or line.lower().startswith("application"):
                    continue
                parts = [p.strip() for p in line.split("\t")]
                if len(parts) >= 2:
                    apps.append(FlatpakApp(appid=parts[0], name=parts[1], origin=remote))

            self._store_all_apps = apps
            self.on_fp_store_apply_filters(self.btn_fp_search)

        run_command_async(argv, on_line=on_line, on_done=on_done)

    def on_fp_install(self, _btn: Gtk.Button) -> None:
        app = self._selected_flatpak_app()
        if app is None:
            self._set_fp_status(t("fp.status.no_selection"))
            return

        self._append_fp_log(f"\n--- Instalacja {app.appid} ---\n")
        self._set_fp_status(t("fp.status.installing"))

        argv = ["flatpak", "install", "-y", app.origin, app.appid]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_fp_status(t("fp.status.installed"))
            else:
                self._set_fp_status(t("fp.status.install_failed"))

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    def on_fp_uninstall(self, _btn: Gtk.Button) -> None:
        app = self._selected_flatpak_app()
        if app is None:
            self._set_fp_status(t("fp.status.no_selection"))
            return

        self._append_fp_log(f"\n--- Odinstalowanie {app.appid} ---\n")
        self._set_fp_status(t("fp.status.uninstalling"))

        argv = ["flatpak", "uninstall", "-y", app.appid]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_fp_status(t("fp.status.uninstalled"))
            else:
                self._set_fp_status(t("fp.status.uninstall_failed"))

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    def on_fp_update_all(self, _btn: Gtk.Button) -> None:
        self._append_fp_log("\n--- Aktualizacja Flatpak ---\n")
        self._set_fp_status(t("fp.status.updating"))

        argv = ["flatpak", "update", "-y"]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_fp_status(t("fp.status.updated"))
            else:
                self._set_fp_status(t("fp.status.update_failed"))

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    # -------------------- Init --------------------

    def _set_initial_status(self) -> None:
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
        if not have_command("pacman"):
            self._set_sys_status(t("sys.status.no_pacman"))

    # -------------------- Flatpak: Installed --------------------

    def on_fp_refresh_installed(self, _btn: Gtk.Button) -> None:
        self.fp_inst_store.clear()
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
            return

        self._set_fp_status(t("fp.status.loading_installed"))
        collected: List[str] = []
        argv = ["flatpak", "list", "--app", "--columns=application,name,origin"]

        def on_line(line: str) -> None:
            collected.append(line)
            self._append_fp_log(line)

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0:
                self._set_fp_status(t("fp.status.search_error"))
                return

            items: List[FlatpakApp] = []
            for raw in "".join(collected).splitlines():
                line = raw.strip()
                if not line or line.lower().startswith("application"):
                    continue
                parts = [p.strip() for p in line.split("\t")]
                if len(parts) >= 3:
                    items.append(FlatpakApp(appid=parts[0], name=parts[1], origin=parts[2]))

            for app in items:
                self.fp_inst_store.append([app.appid, app.name, app.origin])
            self._set_fp_status(t("fp.status.results", n=len(items)))

        run_command_async(argv, on_line=on_line, on_done=on_done)

    # -------------------- Flatpak: Remotes --------------------

    def _selected_remote_name(self) -> Optional[str]:
        sel = self.fp_remote_tree.get_selection()
        model, itr = sel.get_selected()
        if model is None or itr is None:
            return None
        return str(model.get_value(itr, 0))

    def on_fp_refresh_remotes(self, _btn: Gtk.Button) -> None:
        self.fp_remote_store.clear()
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
            return

        self._set_fp_status(t("fp.status.loading_remotes"))
        collected: List[str] = []
        argv = ["flatpak", "remotes", "--columns=name,url,default"]

        def on_line(line: str) -> None:
            collected.append(line)
            self._append_fp_log(line)

        def parse_into_store(text: str) -> int:
            added = 0
            for raw in text.splitlines():
                line = raw.strip()
                # Ignore our own log markers and other non-table lines
                if (
                    not line
                    or line.startswith("$")
                    or line.startswith("---")
                    or line.startswith("[exit=")
                    or line.lower().startswith("error:")
                ):
                    continue
                if not line or line.lower().startswith("name"):
                    continue
                parts = _split_columns(line, min_cols=2)
                if len(parts) < 2:
                    continue
                name, url = parts[0], parts[1]
                if name == "$":
                    continue
                default_raw = parts[2].lower() if len(parts) >= 3 else ""
                is_default = default_raw in ("true", "yes", "1", "default")
                self.fp_remote_store.append([name, url, is_default])
                added += 1
            return added

        def looks_like_unknown_default_column(text: str) -> bool:
            low = text.lower()
            return ("unknown column" in low) and ("default" in low)

        def run_remotes(scope_args: List[str], *, with_default: bool) -> None:
            collected_local: List[str] = []
            cols = "name,url,default" if with_default else "name,url"
            cmd = ["flatpak", "remotes", *scope_args, f"--columns={cols}"]

            def on_line_local(line: str) -> None:
                collected_local.append(line)
                self._append_fp_log(line)

            def on_done_local(res: CommandResult) -> None:
                text = "".join(collected_local)
                if res.exit_code != 0 and with_default and looks_like_unknown_default_column(text):
                    run_remotes(scope_args, with_default=False)
                    return
                if res.exit_code == 0:
                    parse_into_store(text)

                # show/hide Default column depending on support
                try:
                    self.fp_remote_col_default.set_visible(with_default and res.exit_code == 0 and not looks_like_unknown_default_column(text))
                except Exception:
                    pass

                self._sync_store_remote_combo()
                self._set_fp_status(t("fp.status.results", n=len(self.fp_remote_store)))

                try:
                    if self.fp_notebook.get_current_page() == 0:
                        self.on_fp_store_refresh(self.btn_fp_store_refresh)
                except Exception:
                    pass

            run_command_async(cmd, on_line=on_line_local, on_done=on_done_local)

        def on_done(_res: CommandResult) -> None:
            # This legacy path is kept for compatibility with existing async flow.
            # Prefer run_remotes() which handles column compatibility.
            pass

        # Preferred: try user remotes, then system remotes if still empty.
        # 1) user
        run_remotes([], with_default=True)

        # 2) system fallback, scheduled after a short delay so the user list has time to fill
        def maybe_run_system() -> None:
            if len(self.fp_remote_store) == 0:
                run_remotes(["--system"], with_default=True)
            return False

        GLib.timeout_add(300, maybe_run_system)

    def _sync_store_remote_combo(self) -> None:
        # rebuild list of remotes; try to pick default, else cfg
        current = self.combo_fp_store_remote.get_active_id() if hasattr(self, "combo_fp_store_remote") else None
        desired = current or self.cfg.store_remote

        defaults: List[str] = []
        all_names: List[str] = []
        for row in self.fp_remote_store:
            name = str(row[0])
            all_names.append(name)
            if bool(row[2]):
                defaults.append(name)

        if hasattr(self, "combo_fp_store_remote"):
            self.combo_fp_store_remote.remove_all()
            for name in all_names:
                self.combo_fp_store_remote.append(name, name)

            picked = ""
            if desired and desired in all_names:
                picked = desired
            elif defaults:
                picked = defaults[0]
            elif all_names:
                picked = all_names[0]

            if picked:
                self.combo_fp_store_remote.set_active_id(picked)
                if self.cfg.store_remote != picked:
                    self.cfg.store_remote = picked
                    save_config(self.cfg)

    def on_fp_remote_selection_changed(self, _sel) -> None:
        self.on_fp_remote_refresh_apps()

    def on_fp_remote_refresh_apps(self) -> None:
        self.fp_remote_apps_store.clear()
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
            return
        remote = self._selected_remote_name()
        if not remote:
            return
        self._set_fp_status(t("fp.status.remote_apps_loading"))

        collected: List[str] = []
        argv = ["flatpak", "list", "--app", "--columns=application,name,origin"]

        def on_line(line: str) -> None:
            collected.append(line)

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0:
                self._set_fp_status(t("fp.status.search_error"))
                return
            for raw in "".join(collected).splitlines():
                line = raw.strip()
                if not line or line.lower().startswith("application"):
                    continue
                parts = [p.strip() for p in line.split("\t")]
                if len(parts) >= 3 and parts[2] == remote:
                    self.fp_remote_apps_store.append([parts[0], parts[1], parts[2]])
            self._set_fp_status(t("fp.status.results", n=len(self.fp_remote_apps_store)))

        run_command_async(argv, on_line=on_line, on_done=on_done)


    def _selected_remote_app(self) -> Optional[FlatpakApp]:
        sel = self.fp_remote_apps_tree.get_selection()
        model, itr = sel.get_selected()
        if model is None or itr is None:
            return None
        return FlatpakApp(
            appid=str(model.get_value(itr, 0)),
            name=str(model.get_value(itr, 1)),
            origin=str(model.get_value(itr, 2)),
        )

    def on_fp_remote_uninstall_app(self, _btn: Gtk.Button) -> None:
        app = self._selected_remote_app()
        if app is None:
            self._set_fp_status(t("fp.status.no_selection"))
            return
        self._append_fp_log(f"\n--- Odinstalowanie {app.appid} ---\n")
        self._set_fp_status(t("fp.status.uninstalling"))

        argv = ["flatpak", "uninstall", "-y", app.appid]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_fp_status(t("fp.status.uninstalled"))
                self.on_fp_remote_refresh_apps()
                self.on_fp_refresh_installed(self.btn_fp_refresh_installed)
            else:
                self._set_fp_status(t("fp.status.uninstall_failed"))

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    def on_fp_add_remote(self, _btn: Gtk.Button) -> None:
        if not have_command("flatpak"):
            self._set_fp_status(t("fp.status.no_flatpak"))
            return

        dialog = Gtk.Dialog(title=t("dialog.add_remote.title"), transient_for=self, modal=True)
        dialog.add_button(t("dialog.cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(t("dialog.add"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(12)
        box.add(grid)

        lbl_name = Gtk.Label(label=t("dialog.add_remote.name"))
        lbl_name.set_xalign(0)
        ent_name = Gtk.Entry()

        lbl_url = Gtk.Label(label=t("dialog.add_remote.url"))
        lbl_url.set_xalign(0)
        ent_url = Gtk.Entry()

        chk_default = Gtk.CheckButton(label=t("dialog.add_remote.make_default"))
        chk_default.set_active(False)

        grid.attach(lbl_name, 0, 0, 1, 1)
        grid.attach(ent_name, 1, 0, 1, 1)
        grid.attach(lbl_url, 0, 1, 1, 1)
        grid.attach(ent_url, 1, 1, 1, 1)
        grid.attach(chk_default, 1, 2, 1, 1)

        dialog.show_all()
        resp = dialog.run()
        name = ent_name.get_text().strip()
        url = ent_url.get_text().strip()
        make_default = chk_default.get_active()
        dialog.destroy()

        if resp != Gtk.ResponseType.OK:
            return
        if not name or not url:
            self._set_fp_status(t("fp.status.remote_add_failed"))
            return

        self._set_fp_status(t("fp.status.loading_remotes"))
        argv = ["flatpak", "remote-add", "--if-not-exists", name, url]

        def on_done(res: CommandResult) -> None:
            if res.exit_code != 0:
                self._set_fp_status(t("fp.status.remote_add_failed"))
                return
            if make_default:
                run_command_async(
                    ["flatpak", "remote-modify", "--default", name],
                    on_line=self._append_fp_log,
                    on_done=lambda r: self._set_fp_status(
                        t("fp.status.remote_default_set") if r.exit_code == 0 else t("fp.status.remote_default_failed")
                    ),
                )
            else:
                self._set_fp_status(t("fp.status.remote_added"))
            self.on_fp_refresh_remotes(self.btn_fp_refresh_remotes)

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    def on_fp_set_default_remote(self, _btn: Gtk.Button) -> None:
        name = self._selected_remote_name()
        if not name:
            self._set_fp_status(t("fp.status.no_selection"))
            return
        argv = ["flatpak", "remote-modify", "--default", name]

        def on_done(res: CommandResult) -> None:
            if res.exit_code == 0:
                self._set_fp_status(t("fp.status.remote_default_set"))
                self.on_fp_refresh_remotes(self.btn_fp_refresh_remotes)
            else:
                self._set_fp_status(t("fp.status.remote_default_failed"))

        run_command_async(argv, on_line=self._append_fp_log, on_done=on_done)

    # -------------------- Settings --------------------

    def on_language_changed(self, combo: Gtk.ComboBoxText) -> None:
        lang = combo.get_active_id() or "pl"
        set_language(lang)
        self.cfg.language = lang
        save_config(self.cfg)

        self.fp_label_store.set_text(t("fp.subtab.store"))
        self.fp_label_installed.set_text(t("fp.subtab.installed"))
        self.fp_label_remotes.set_text(t("fp.subtab.remotes"))
        self._apply_translations()

        # refresh category label
        self._populate_categories()


def run() -> int:
    win = VistullaUpdaterWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0
