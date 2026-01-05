from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoftwareSelection:
    gamers: bool = False
    creators: bool = False
    accountants: bool = False
    developers: bool = False

    nvidia_driver: bool = False

    # Gamers
    gamers_steam: bool = False
    gamers_lutris: bool = False
    gamers_wine: bool = False
    gamers_mangohud: bool = False
    gamers_gamemode: bool = False

    # Creators
    creators_gimp: bool = False
    creators_inkscape: bool = False
    creators_blender: bool = False
    creators_kdenlive: bool = False
    creators_audacity: bool = False

    # Accountants
    accountants_libreoffice: bool = False
    accountants_gnucash: bool = False

    # Developers
    developers_git: bool = False
    developers_base_devel: bool = False
    developers_python: bool = False
    developers_nodejs: bool = False
    developers_vscode: bool = False


def selection_from_config(install) -> SoftwareSelection:
    return SoftwareSelection(
        gamers=bool(getattr(install, "profile_gamers", False)),
        creators=bool(getattr(install, "profile_creators", False)),
        accountants=bool(getattr(install, "profile_accountants", False)),
        developers=bool(getattr(install, "profile_developers", False)),
        nvidia_driver=bool(getattr(install, "driver_nvidia", False)),
        gamers_steam=bool(getattr(install, "gamers_steam", False)),
        gamers_lutris=bool(getattr(install, "gamers_lutris", False)),
        gamers_wine=bool(getattr(install, "gamers_wine", False)),
        gamers_mangohud=bool(getattr(install, "gamers_mangohud", False)),
        gamers_gamemode=bool(getattr(install, "gamers_gamemode", False)),
        creators_gimp=bool(getattr(install, "creators_gimp", False)),
        creators_inkscape=bool(getattr(install, "creators_inkscape", False)),
        creators_blender=bool(getattr(install, "creators_blender", False)),
        creators_kdenlive=bool(getattr(install, "creators_kdenlive", False)),
        creators_audacity=bool(getattr(install, "creators_audacity", False)),
        accountants_libreoffice=bool(getattr(install, "accountants_libreoffice", False)),
        accountants_gnucash=bool(getattr(install, "accountants_gnucash", False)),
        developers_git=bool(getattr(install, "developers_git", False)),
        developers_base_devel=bool(getattr(install, "developers_base_devel", False)),
        developers_python=bool(getattr(install, "developers_python", False)),
        developers_nodejs=bool(getattr(install, "developers_nodejs", False)),
        developers_vscode=bool(getattr(install, "developers_vscode", False)),
    )


def arch_packages_for_selection(sel: SoftwareSelection) -> list[str]:
    pkgs: list[str] = []

    # Drivers
    if sel.nvidia_driver:
        pkgs += ["nvidia", "nvidia-utils", "lib32-nvidia-utils"]

    # Profiles
    if sel.gamers:
        # Prefer Flatpak for GUI apps (Steam/Lutris).
        if sel.gamers_wine:
            pkgs += ["wine", "winetricks"]
        if sel.gamers_mangohud:
            pkgs += ["mangohud"]
        if sel.gamers_gamemode:
            pkgs += ["gamemode"]

    if sel.creators:
        # Prefer Flatpak for GUI apps.
        pass

    if sel.accountants:
        # Prefer Flatpak for GUI apps.
        pass

    if sel.developers:
        if sel.developers_git:
            pkgs += ["git"]
        if sel.developers_base_devel:
            pkgs += ["base-devel"]
        if sel.developers_python:
            pkgs += ["python"]
        if sel.developers_nodejs:
            pkgs += ["nodejs", "npm"]

    # Deduplicate, stable order
    seen: set[str] = set()
    out: list[str] = []
    for p in pkgs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def flatpak_appids_for_selection(sel: SoftwareSelection) -> list[str]:
    apps: list[str] = []

    # Profiles
    if sel.gamers:
        if sel.gamers_steam:
            apps += ["com.valvesoftware.Steam"]
        if sel.gamers_lutris:
            apps += ["net.lutris.Lutris"]

    if sel.creators:
        if sel.creators_gimp:
            apps += ["org.gimp.GIMP"]
        if sel.creators_inkscape:
            apps += ["org.inkscape.Inkscape"]
        if sel.creators_blender:
            apps += ["org.blender.Blender"]
        if sel.creators_kdenlive:
            apps += ["org.kde.kdenlive"]
        if sel.creators_audacity:
            apps += ["org.audacityteam.Audacity"]

    if sel.accountants:
        if sel.accountants_libreoffice:
            apps += ["org.libreoffice.LibreOffice"]
        if sel.accountants_gnucash:
            apps += ["org.gnucash.GnuCash"]

    if sel.developers:
        if sel.developers_vscode:
            apps += ["com.visualstudio.code"]

    # Deduplicate, stable order
    seen: set[str] = set()
    out: list[str] = []
    for a in apps:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out
