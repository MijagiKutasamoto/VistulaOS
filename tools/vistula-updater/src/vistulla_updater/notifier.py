from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass

from .config import load_config
from .i18n import set_language, t


@dataclass(frozen=True)
class UpdatesResult:
    count: int


def _run_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "LC_ALL": "C",
                "LANG": "C",
            },
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def _count_updates_checkupdates() -> int | None:
    # Arch: checkupdates returns 0 with updates, 2 with none. Output lines == packages.
    cp = _run_capture(["checkupdates"])
    if cp.returncode == 0:
        return len([ln for ln in cp.stdout.splitlines() if ln.strip()])
    if cp.returncode == 2:
        return 0
    return None


def _count_updates_pacman_qu() -> int | None:
    # Fallback if checkupdates isn't present.
    cp = _run_capture(["pacman", "-Qu"])
    if cp.returncode == 0:
        return len([ln for ln in cp.stdout.splitlines() if ln.strip()])
    # Non-zero can happen e.g. if db locked; treat as unknown.
    return None


def get_updates_count() -> UpdatesResult | None:
    count = _count_updates_checkupdates()
    if count is None:
        count = _count_updates_pacman_qu()
    if count is None:
        return None
    return UpdatesResult(count=count)


def _notify(title: str, body: str, icon: str | None) -> None:
    cmd = ["notify-send", title, body]
    if icon:
        cmd.extend(["-i", icon])

    cp = _run_capture(cmd)
    if cp.returncode != 0:
        # Don't crash background loop; print to stderr for journald/user logs.
        msg = (cp.stderr or cp.stdout).strip()
        if msg:
            print(f"notify-send failed: {msg}", file=sys.stderr)


def run_once() -> None:
    cfg = load_config()

    lang = getattr(cfg, "language", "pl")
    set_language(lang)
    title = t("notify.title")

    result = get_updates_count()
    if result is None:
        return

    if result.count <= 0:
        return

    body = t("notify.updates_available", n=result.count)

    # Prefer icon from VistulaOS theme if present; otherwise fallback to icon name.
    icon_name: str | None = None
    candidate_paths = [
        "/usr/share/icons/VistulaOS/scalable/apps/system-software-update.svg",
        "/usr/local/share/icons/VistulaOS/scalable/apps/system-software-update.svg",
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            icon_name = p
            break
    if icon_name is None:
        icon_name = "system-software-update"

    _notify(title=title, body=body, icon=icon_name)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Minimal CLI:
    # - once: run check once and exit
    # - loop: check now, then every hour
    mode = "loop"
    if argv:
        mode = argv[0]

    if mode == "once":
        run_once()
        return 0

    interval_sec = 3600
    while True:
        try:
            run_once()
        except Exception as exc:  # noqa: BLE001
            print(f"notifier error: {exc}", file=sys.stderr)
        time.sleep(interval_sec)


if __name__ == "__main__":
    raise SystemExit(main())
