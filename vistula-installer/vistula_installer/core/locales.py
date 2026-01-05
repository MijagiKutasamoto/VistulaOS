from __future__ import annotations

import logging
from pathlib import Path

from vistula_installer.core.executor import CommandExecutor


log = logging.getLogger(__name__)


def _read_supported_file(path: Path) -> list[str]:
    locales: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # glibc SUPPORTED format: "en_US.UTF-8 UTF-8" (locale + charmap)
            locales.append(line.split()[0])
    except Exception as e:
        log.debug("Failed reading %s: %s", path, e)
    return locales


def list_supported_locales(executor: CommandExecutor, *, utf8_only: bool = True) -> list[str]:
    """Return locales supported by current environment.

    Prefer glibc's `/usr/share/i18n/SUPPORTED` when available; otherwise fall back
    to `locale -a`.

    This is intended for populating the UI locale dropdown.
    """

    candidates: list[str] = []

    supported = Path("/usr/share/i18n/SUPPORTED")
    if supported.exists():
        candidates = _read_supported_file(supported)

    if not candidates:
        res = executor.run(["locale", "-a"], check=False, allow_in_dry_run=True)
        if res.returncode == 0 and res.stdout:
            candidates = [l.strip() for l in res.stdout.splitlines() if l.strip()]

    if utf8_only:
        out = [l for l in candidates if "UTF-8" in l or "utf8" in l]
    else:
        out = candidates

    # Deduplicate + stable sort
    uniq = sorted(set(out), key=str.casefold)
    return uniq
