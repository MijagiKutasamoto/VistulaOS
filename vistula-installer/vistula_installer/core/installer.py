from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from vistula_installer.core.executor import CommandExecutor
from vistula_installer.core.config import AppConfig
from vistula_installer.core.software import (
    selection_from_config,
    arch_packages_for_selection,
    flatpak_appids_for_selection,
)


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiskInfo:
    path: str
    size: str
    model: str


@dataclass(frozen=True)
class PartitionInfo:
    path: str
    size: str
    fstype: str
    label: str
    mountpoint: str


def list_disks(executor: CommandExecutor) -> list[DiskInfo]:
    # lsblk JSON is widely available.
    res = executor.run(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MODEL"], check=True, allow_in_dry_run=True)

    data = json.loads(res.stdout)
    out: list[DiskInfo] = []
    for dev in data.get("blockdevices", []) or []:
        if dev.get("type") != "disk":
            continue
        name = dev.get("name")
        if not name:
            continue
        out.append(
            DiskInfo(
                path=f"/dev/{name}",
                size=str(dev.get("size", "")),
                model=str(dev.get("model", "")).strip(),
            )
        )
    return out


def list_partitions(executor: CommandExecutor) -> list[PartitionInfo]:
    res = executor.run(
        ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT"],
        check=True,
        allow_in_dry_run=True,
    )
    data = json.loads(res.stdout)
    out: list[PartitionInfo] = []

    def walk(nodes: list[dict]) -> None:
        for dev in nodes or []:
            if dev.get("type") == "part":
                name = dev.get("name")
                if name:
                    out.append(
                        PartitionInfo(
                            path=f"/dev/{name}",
                            size=str(dev.get("size", "")),
                            fstype=str(dev.get("fstype", "") or ""),
                            label=str(dev.get("label", "") or ""),
                            mountpoint=str(dev.get("mountpoint", "") or ""),
                        )
                    )
            children = dev.get("children")
            if isinstance(children, list) and children:
                walk(children)

    walk(data.get("blockdevices", []) or [])
    return out


def _disk_prefix(disk: str) -> str:
    # /dev/sda -> /dev/sda
    # /dev/nvme0n1 -> /dev/nvme0n1p
    # /dev/mmcblk0 -> /dev/mmcblk0p
    if "nvme" in disk or "mmcblk" in disk:
        return disk + "p"
    return disk


def _blkid_export(executor: CommandExecutor, dev: str) -> dict[str, str]:
    res = executor.run(["blkid", "-o", "export", dev], check=False, allow_in_dry_run=True)
    if res.returncode != 0:
        return {}
    out: dict[str, str] = {}
    for line in (res.stdout or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _fstab_ident(executor: CommandExecutor, dev: str) -> tuple[str, str] | None:
    info = _blkid_export(executor, dev)
    partuuid = info.get("PARTUUID")
    uuid = info.get("UUID")
    if partuuid:
        return ("PARTUUID", partuuid)
    if uuid:
        return ("UUID", uuid)
    return None


def _fstype(executor: CommandExecutor, dev: str, fallback: str) -> str:
    info = _blkid_export(executor, dev)
    return info.get("TYPE") or fallback


def build_fstab_content(
    *,
    executor: CommandExecutor,
    root_part: str,
    efi_part: str | None,
    home_part: str | None,
    swap_part: str | None,
) -> str:
    """Build `/etc/fstab` content using PARTUUID/UUID when available.

    Falls back to raw device paths if identifiers cannot be read.
    """

    def devref(dev: str) -> str:
        ident = _fstab_ident(executor, dev)
        if ident is None:
            return dev
        k, v = ident
        return f"{k}={v}"

    root_fs = _fstype(executor, root_part, "ext4")
    lines: list[str] = []
    lines.append(f"{devref(root_part)} / {root_fs} defaults 0 1\n")

    if efi_part:
        efi_fs = _fstype(executor, efi_part, "vfat")
        lines.append(f"{devref(efi_part)} /boot/efi {efi_fs} umask=0077 0 1\n")

    if home_part:
        home_fs = _fstype(executor, home_part, "ext4")
        lines.append(f"{devref(home_part)} /home {home_fs} defaults 0 2\n")

    if swap_part:
        lines.append(f"{devref(swap_part)} none swap sw 0 0\n")

    return "".join(lines)


def _write_fstab(
    *,
    target: Path,
    executor: CommandExecutor,
    root_part: str,
    efi_part: str | None,
    home_part: str | None,
    swap_part: str | None,
) -> None:
    fstab = target / "etc" / "fstab"
    fstab.parent.mkdir(parents=True, exist_ok=True)

    fstab_content = build_fstab_content(
        executor=executor,
        root_part=root_part,
        efi_part=efi_part,
        home_part=home_part,
        swap_part=swap_part,
    )
    if executor.dry_run:
        log.info("[DRY-RUN] write %s:\n%s", fstab, fstab_content)
    else:
        fstab.write_text(fstab_content, encoding="utf-8")


class InstallerEngine:
    def __init__(self, *, config: AppConfig, executor: CommandExecutor) -> None:
        self._config = config
        self._executor = executor

    def validate_ready(self) -> None:
        cfg = self._config.install
        if not cfg.target_disk:
            raise ValueError("No target disk selected")
        if not cfg.erase_disk:
            if not cfg.root_partition:
                raise ValueError("No root partition selected")
            if Path("/sys/firmware/efi").exists() and not cfg.efi_partition:
                raise ValueError("EFI partition is required for UEFI systems")
        if not cfg.password:
            raise ValueError("Password is required")

    def run_install(self, *, progress_cb=None) -> None:
        """Run installation steps.

        This is intentionally conservative: only 'erase whole disk' flow is implemented.
        """
        self.validate_ready()

        if os.geteuid() != 0 and not self._executor.dry_run:
            raise PermissionError("Installer must be run as root (or use --dry-run)")

        disk = self._config.install.target_disk
        assert disk is not None
        cfg = self._config.install

        def step(pct: int, msg: str) -> None:
            log.info("%s%% %s", pct, msg)
            if progress_cb:
                progress_cb(pct, msg)

        is_efi = Path("/sys/firmware/efi").exists()
        efi_part: str | None = None
        home_part: str | None = None
        swap_part: str | None = None

        if cfg.erase_disk:
            # Partitioning (GPT + EFI + root) + format
            step(5, "Partitioning disk")
            self._executor.run(["wipefs", "-a", disk])
            self._executor.run(["parted", "-s", disk, "mklabel", "gpt"])
            self._executor.run(["parted", "-s", disk, "mkpart", "EFI", "fat32", "1MiB", "513MiB"])
            self._executor.run(["parted", "-s", disk, "set", "1", "esp", "on"])
            self._executor.run(["parted", "-s", disk, "mkpart", "ROOT", "ext4", "513MiB", "100%"])

            # Partition node naming: /dev/sda1 vs /dev/nvme0n1p1, /dev/mmcblk0p1
            if "nvme" in disk or "mmcblk" in disk:
                efi_part = disk + "p1"
                root_part = disk + "p2"
            else:
                efi_part = disk + "1"
                root_part = disk + "2"

            step(15, "Formatting partitions")
            self._executor.run(["mkfs.vfat", "-F", "32", efi_part])
            self._executor.run(["mkfs.ext4", "-F", root_part])
        else:
            # Manual partitioning flow
            root_part = cfg.root_partition
            efi_part = cfg.efi_partition or None
            home_part = cfg.home_partition or None
            swap_part = cfg.swap_partition or None

            step(10, "Formatting partitions")
            if cfg.format_root:
                self._executor.run(["mkfs.ext4", "-F", root_part])
            if efi_part and cfg.format_efi:
                self._executor.run(["mkfs.vfat", "-F", "32", efi_part])
            if home_part and cfg.format_home:
                self._executor.run(["mkfs.ext4", "-F", home_part])
            if swap_part and cfg.format_swap:
                self._executor.run(["mkswap", swap_part])

        target = Path("/mnt/vistula-target")
        step(25, "Mounting target")
        self._executor.run(["mkdir", "-p", str(target)])
        self._executor.run(["mount", root_part, str(target)])
        if home_part:
            self._executor.run(["mkdir", "-p", str(target / "home")])
            self._executor.run(["mount", home_part, str(target / "home")])
        if efi_part:
            self._executor.run(["mkdir", "-p", str(target / "boot" / "efi")])
            self._executor.run(["mount", efi_part, str(target / "boot" / "efi")])
        if swap_part:
            # Best-effort; helps installers on low RAM.
            self._executor.run(["swapon", swap_part], check=False)

        # Copy filesystem from live root
        step(45, "Copying system files")
        self._executor.run([
            "rsync",
            "-aAXH",
            "--numeric-ids",
            "--exclude=/dev/*",
            "--exclude=/proc/*",
            "--exclude=/sys/*",
            "--exclude=/run/*",
            "--exclude=/tmp/*",
            "--exclude=/mnt/*",
            "--exclude=/media/*",
            "--exclude=/lost+found",
            "/",
            str(target),
        ])

        step(60, "Writing fstab")
        _write_fstab(
            target=target,
            executor=self._executor,
            root_part=root_part,
            efi_part=efi_part,
            home_part=home_part,
            swap_part=swap_part,
        )

        # Chroot prep and GRUB install
        step(75, "Preparing chroot")
        for d in ("dev", "proc", "sys"):
            self._executor.run(["mount", "--bind", f"/{d}", str(target / d)])

        # System identity + user
        step(80, "Configuring system")
        hostname_path = target / "etc" / "hostname"
        hosts_path = target / "etc" / "hosts"
        hostname = self._config.install.hostname
        hosts_content = f"127.0.0.1\tlocalhost\n127.0.1.1\t{hostname}\n\n::1\tlocalhost ip6-localhost ip6-loopback\n"
        if self._executor.dry_run:
            log.info("[DRY-RUN] write %s: %s", hostname_path, hostname)
            log.info("[DRY-RUN] write %s:\n%s", hosts_path, hosts_content)
        else:
            hostname_path.parent.mkdir(parents=True, exist_ok=True)
            hostname_path.write_text(hostname + "\n", encoding="utf-8")
            hosts_path.write_text(hosts_content, encoding="utf-8")

        # Timezone (best-effort, distro-dependent)
        tz = self._config.install.timezone
        if self._executor.dry_run:
            log.info("[DRY-RUN] set timezone to %s", tz)
        else:
            zoneinfo = target / "usr/share/zoneinfo" / tz
            localtime = target / "etc" / "localtime"
            if zoneinfo.exists():
                localtime.parent.mkdir(parents=True, exist_ok=True)
                if localtime.exists() or localtime.is_symlink():
                    localtime.unlink()
                localtime.symlink_to(zoneinfo)
            (target / "etc" / "timezone").write_text(tz + "\n", encoding="utf-8")

        # Keyboard (Debian-like)
        kbd = self._config.install.keyboard_layout
        keyboard_file = target / "etc" / "default" / "keyboard"
        keyboard_content = f"XKBLAYOUT=\"{kbd}\"\nXKBMODEL=\"pc105\"\nXKBVARIANT=\"\"\nXKBOPTIONS=\"\"\nBACKSPACE=\"guess\"\n"
        if self._executor.dry_run:
            log.info("[DRY-RUN] write %s:\n%s", keyboard_file, keyboard_content)
        else:
            keyboard_file.parent.mkdir(parents=True, exist_ok=True)
            keyboard_file.write_text(keyboard_content, encoding="utf-8")

        # Locale (Arch-like)
        step(82, "Configuring locale")
        locale = self._config.install.locale
        locale_conf = target / "etc" / "locale.conf"
        vconsole = target / "etc" / "vconsole.conf"
        if self._executor.dry_run:
            log.info("[DRY-RUN] write %s: LANG=%s", locale_conf, locale)
            log.info("[DRY-RUN] write %s: KEYMAP=%s", vconsole, kbd)
        else:
            locale_conf.parent.mkdir(parents=True, exist_ok=True)
            locale_conf.write_text(f"LANG={locale}\n", encoding="utf-8")
            vconsole.write_text(f"KEYMAP={kbd}\n", encoding="utf-8")

        locale_gen = target / "etc" / "locale.gen"
        if locale_gen.exists():
            if self._executor.dry_run:
                log.info("[DRY-RUN] update %s (all=%s)", locale_gen, self._config.install.generate_all_locales_arch)
            else:
                lines = locale_gen.read_text(encoding="utf-8", errors="ignore").splitlines(True)
                out_lines: list[str] = []
                if self._config.install.generate_all_locales_arch:
                    for line in lines:
                        if line.lstrip().startswith("#") and ".UTF-8" in line:
                            out_lines.append(line.lstrip()[1:])
                        else:
                            out_lines.append(line)
                else:
                    for line in lines:
                        stripped = line.lstrip()
                        if stripped.startswith("#") and locale in stripped:
                            out_lines.append(stripped[1:])
                        else:
                            out_lines.append(line)
                locale_gen.write_text("".join(out_lines), encoding="utf-8")

            # Generate locales if tool exists
            self._executor.run(["chroot", str(target), "bash", "-lc", "command -v locale-gen >/dev/null 2>&1 && locale-gen || true"], check=False)

        # Network
        step(84, "Configuring network")
        if self._config.install.enable_networkmanager:
            self._executor.run(
                ["chroot", str(target), "bash", "-lc", "command -v systemctl >/dev/null 2>&1 && systemctl enable NetworkManager || true"],
                check=False,
            )

        ssid = self._config.install.wifi_ssid.strip()
        wifipass = self._config.install.wifi_password
        if ssid:
            nm_dir = target / "etc" / "NetworkManager" / "system-connections"
            nm_dir.mkdir(parents=True, exist_ok=True)
            uuid = str(uuid4())
            content = (
                "[connection]\n"
                f"id={ssid}\n"
                f"uuid={uuid}\n"
                "type=wifi\n"
                "autoconnect=true\n"
                "\n"
                "[wifi]\n"
                f"ssid={ssid}\n"
                "mode=infrastructure\n"
                "\n"
                "[wifi-security]\n"
                "key-mgmt=wpa-psk\n"
                f"psk={wifipass}\n"
                "\n"
                "[ipv4]\n"
                "method=auto\n"
                "\n"
                "[ipv6]\n"
                "method=auto\n"
            )
            nm_file = nm_dir / f"{ssid}.nmconnection"
            if self._executor.dry_run:
                log.info("[DRY-RUN] write %s (wifi profile)", nm_file)
            else:
                nm_file.write_text(content, encoding="utf-8")
                os.chmod(nm_file, 0o600)

        step(85, "Creating user")
        user = self._config.install.username
        pwd = self._config.install.password
        self._executor.run(["chroot", str(target), "useradd", "-m", "-s", "/bin/bash", user], check=False)
        self._executor.run(["chroot", str(target), "chpasswd"], input_text=f"{user}:{pwd}\n")

        # Optional packages (Arch)
        step(88, "Installing optional software")
        sel = selection_from_config(self._config.install)
        pkgs = arch_packages_for_selection(sel)
        if pkgs:
            pacman = target / "usr/bin/pacman"
            if pacman.exists():
                self._executor.run(["chroot", str(target), "pacman", "-S", "--noconfirm", "--needed", *pkgs], check=False)
            else:
                log.info("Skipping optional packages: pacman not found in target")

            # Optional Flatpak apps (best-effort)
            flatpaks = list(self._config.install.flatpak_apps or [])
            flatpaks += flatpak_appids_for_selection(sel)
            # Deduplicate, stable order
            seen: set[str] = set()
            flatpaks = [a for a in flatpaks if not (a in seen or seen.add(a))]
        if flatpaks:
            flatpak_bin = target / "usr/bin/flatpak"
            if flatpak_bin.exists():
                # Add flathub remote if possible
                self._executor.run(
                    [
                        "chroot",
                        str(target),
                        "flatpak",
                        "remote-add",
                        "--if-not-exists",
                        "flathub",
                        "https://flathub.org/repo/flathub.flatpakrepo",
                    ],
                    check=False,
                )
                for appid in flatpaks:
                    self._executor.run(["chroot", str(target), "flatpak", "install", "-y", "flathub", appid], check=False)
            else:
                log.info("Skipping Flatpak apps: flatpak not found in target")

        step(90, "Installing bootloader")
        if is_efi:
            self._executor.run(
                [
                    "chroot",
                    str(target),
                    "grub-install",
                    "--target=x86_64-efi",
                    "--efi-directory=/boot/efi",
                    "--bootloader-id=VistulaOS",
                ]
            )
        else:
            self._executor.run(
                [
                    "chroot",
                    str(target),
                    "grub-install",
                    "--target=i386-pc",
                    disk,
                ]
            )

        # update-grub is distro-specific; fall back to grub-mkconfig.
        self._executor.run(
            [
                "chroot",
                str(target),
                "bash",
                "-lc",
                "command -v update-grub >/dev/null 2>&1 && update-grub || grub-mkconfig -o /boot/grub/grub.cfg",
            ]
        )

        step(95, "Finalizing")
        if swap_part:
            self._executor.run(["swapoff", swap_part], check=False)
        # Unmount everything under the target mountpoint
        self._executor.run(["umount", "-R", str(target)], check=False)

        step(100, "Done")
