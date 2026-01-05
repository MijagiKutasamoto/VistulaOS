from __future__ import annotations

import logging
from pathlib import Path

from vistula_installer.core.executor import CommandExecutor


log = logging.getLogger(__name__)


def list_timezones(executor: CommandExecutor) -> list[str]:
    """Return a list of IANA timezones.

    Prefer `/usr/share/zoneinfo/zone1970.tab` when present; fall back to
    `timedatectl list-timezones`.
    """

    zone_tab = Path("/usr/share/zoneinfo/zone1970.tab")
    zones: list[str] = []

    if zone_tab.exists():
        try:
            for raw in zone_tab.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # Columns: country-code, coordinates, zone, comments
                parts = line.split("\t")
                if len(parts) >= 3:
                    zones.append(parts[2].strip())
        except Exception as e:
            log.debug("Failed reading %s: %s", zone_tab, e)

    if not zones:
        res = executor.run(["timedatectl", "list-timezones"], check=False, allow_in_dry_run=True)
        if res.returncode == 0 and res.stdout:
            zones = [z.strip() for z in res.stdout.splitlines() if z.strip()]

    return sorted(set(zones), key=str.casefold)
