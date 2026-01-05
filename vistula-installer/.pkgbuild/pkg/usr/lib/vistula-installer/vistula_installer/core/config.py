from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _xdg_config_home() -> Path:
    return Path.home() / ".config"


def _xdg_state_home() -> Path:
    return Path.home() / ".local" / "state"


@dataclass
class RuntimeConfig:
    dry_run: bool = True


@dataclass
class UIConfig:
    language: str = "pl"
    gtk_theme: str | None = None


@dataclass
class InstallConfig:
    target_disk: str | None = None  # e.g. /dev/sda
    erase_disk: bool = False

    # Manual partitioning
    root_partition: str = ""  # required when erase_disk=False
    efi_partition: str = ""  # recommended/required on UEFI
    home_partition: str = ""  # optional
    swap_partition: str = ""  # optional
    format_root: bool = True
    format_efi: bool = False
    format_home: bool = False
    format_swap: bool = False
    hostname: str = "vistula"
    username: str = "user"
    password: str = ""
    timezone: str = "Europe/Warsaw"
    keyboard_layout: str = "pl"

    # Locale / languages
    locale: str = "pl_PL.UTF-8"
    generate_all_locales_arch: bool = False

    # Network
    enable_networkmanager: bool = True
    wifi_ssid: str = ""
    wifi_password: str = ""

    # Optional software bundles
    profile_gamers: bool = False
    profile_creators: bool = False
    profile_accountants: bool = False
    profile_developers: bool = False
    driver_nvidia: bool = False

    # Bundle details (Arch packages)
    gamers_steam: bool = False
    gamers_lutris: bool = False
    gamers_wine: bool = False
    gamers_mangohud: bool = False
    gamers_gamemode: bool = False

    creators_gimp: bool = False
    creators_inkscape: bool = False
    creators_blender: bool = False
    creators_kdenlive: bool = False
    creators_audacity: bool = False

    accountants_libreoffice: bool = False
    accountants_gnucash: bool = False

    developers_git: bool = False
    developers_base_devel: bool = False
    developers_python: bool = False
    developers_nodejs: bool = False
    developers_vscode: bool = False

    # Flatpak apps (optional)
    flatpak_apps: list[str] = field(default_factory=list)


@dataclass
class PathConfig:
    config_dir: str
    state_dir: str
    log_file: str


@dataclass
class AppConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    install: InstallConfig = field(default_factory=InstallConfig)
    paths: PathConfig = field(default_factory=lambda: PathConfig(
        config_dir=str(_xdg_config_home() / "vistula-installer"),
        state_dir=str(_xdg_state_home() / "vistula-installer"),
        log_file=str(_xdg_state_home() / "vistula-installer" / "installer.log"),
    ))

    @property
    def config_path(self) -> Path:
        return Path(self.paths.config_dir) / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        path = cfg.config_path
        if not path.exists():
            cfg._ensure_dirs()
            return cfg

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cfg._ensure_dirs()
            return cfg

        # Shallow, tolerant merge.
        cfg.ui.language = str(data.get("ui", {}).get("language", cfg.ui.language))
        cfg.ui.gtk_theme = data.get("ui", {}).get("gtk_theme", cfg.ui.gtk_theme)

        install = data.get("install", {})
        cfg.install.target_disk = install.get("target_disk", cfg.install.target_disk)
        cfg.install.erase_disk = bool(install.get("erase_disk", cfg.install.erase_disk))

        cfg.install.root_partition = str(install.get("root_partition", cfg.install.root_partition) or "")
        cfg.install.efi_partition = str(install.get("efi_partition", cfg.install.efi_partition) or "")
        cfg.install.home_partition = str(install.get("home_partition", cfg.install.home_partition) or "")
        cfg.install.swap_partition = str(install.get("swap_partition", cfg.install.swap_partition) or "")
        cfg.install.format_root = bool(install.get("format_root", cfg.install.format_root))
        cfg.install.format_efi = bool(install.get("format_efi", cfg.install.format_efi))
        cfg.install.format_home = bool(install.get("format_home", cfg.install.format_home))
        cfg.install.format_swap = bool(install.get("format_swap", cfg.install.format_swap))
        cfg.install.hostname = str(install.get("hostname", cfg.install.hostname))
        cfg.install.username = str(install.get("username", cfg.install.username))
        cfg.install.timezone = str(install.get("timezone", cfg.install.timezone))
        cfg.install.keyboard_layout = str(install.get("keyboard_layout", cfg.install.keyboard_layout))

        cfg.install.locale = str(install.get("locale", cfg.install.locale))
        cfg.install.generate_all_locales_arch = bool(
            install.get("generate_all_locales_arch", cfg.install.generate_all_locales_arch)
        )

        cfg.install.enable_networkmanager = bool(
            install.get("enable_networkmanager", cfg.install.enable_networkmanager)
        )
        cfg.install.wifi_ssid = str(install.get("wifi_ssid", cfg.install.wifi_ssid))

        cfg.install.profile_gamers = bool(install.get("profile_gamers", cfg.install.profile_gamers))
        cfg.install.profile_creators = bool(install.get("profile_creators", cfg.install.profile_creators))
        cfg.install.profile_accountants = bool(
            install.get("profile_accountants", cfg.install.profile_accountants)
        )
        cfg.install.profile_developers = bool(
            install.get("profile_developers", cfg.install.profile_developers)
        )
        cfg.install.driver_nvidia = bool(install.get("driver_nvidia", cfg.install.driver_nvidia))

        cfg.install.gamers_steam = bool(install.get("gamers_steam", cfg.install.gamers_steam))
        cfg.install.gamers_lutris = bool(install.get("gamers_lutris", cfg.install.gamers_lutris))
        cfg.install.gamers_wine = bool(install.get("gamers_wine", cfg.install.gamers_wine))
        cfg.install.gamers_mangohud = bool(install.get("gamers_mangohud", cfg.install.gamers_mangohud))
        cfg.install.gamers_gamemode = bool(install.get("gamers_gamemode", cfg.install.gamers_gamemode))

        cfg.install.creators_gimp = bool(install.get("creators_gimp", cfg.install.creators_gimp))
        cfg.install.creators_inkscape = bool(install.get("creators_inkscape", cfg.install.creators_inkscape))
        cfg.install.creators_blender = bool(install.get("creators_blender", cfg.install.creators_blender))
        cfg.install.creators_kdenlive = bool(install.get("creators_kdenlive", cfg.install.creators_kdenlive))
        cfg.install.creators_audacity = bool(install.get("creators_audacity", cfg.install.creators_audacity))

        cfg.install.accountants_libreoffice = bool(
            install.get("accountants_libreoffice", cfg.install.accountants_libreoffice)
        )
        cfg.install.accountants_gnucash = bool(
            install.get("accountants_gnucash", cfg.install.accountants_gnucash)
        )

        cfg.install.developers_git = bool(install.get("developers_git", cfg.install.developers_git))
        cfg.install.developers_base_devel = bool(
            install.get("developers_base_devel", cfg.install.developers_base_devel)
        )
        cfg.install.developers_python = bool(install.get("developers_python", cfg.install.developers_python))
        cfg.install.developers_nodejs = bool(install.get("developers_nodejs", cfg.install.developers_nodejs))
        cfg.install.developers_vscode = bool(install.get("developers_vscode", cfg.install.developers_vscode))

        cfg.install.flatpak_apps = list(install.get("flatpak_apps", cfg.install.flatpak_apps) or [])

        cfg._ensure_dirs()
        return cfg

    def save(self) -> None:
        self._ensure_dirs()
        payload = asdict(self)
        # Never persist plaintext password.
        payload["install"]["password"] = ""
        # Never persist plaintext Wi-Fi password.
        payload["install"]["wifi_password"] = ""
        self.config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _ensure_dirs(self) -> None:
        Path(self.paths.config_dir).mkdir(parents=True, exist_ok=True)
        Path(self.paths.state_dir).mkdir(parents=True, exist_ok=True)
        Path(self.paths.log_file).parent.mkdir(parents=True, exist_ok=True)
