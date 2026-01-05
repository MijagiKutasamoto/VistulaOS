from __future__ import annotations

import logging
from dataclasses import dataclass

from vistula_installer.core.executor import CommandExecutor


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: int | None = None
    security: str | None = None


def list_wifi_networks(executor: CommandExecutor) -> list[WifiNetwork]:
    """Best-effort Wi-Fi scan.

    Uses NetworkManager (`nmcli`) if available. Returns empty list if not.
    """
    res = executor.run(
        [
            "nmcli",
            "-t",
            "-f",
            "SSID,SIGNAL,SECURITY",
            "dev",
            "wifi",
            "list",
            "--rescan",
            "yes",
        ],
        check=False,
        allow_in_dry_run=True,
    )

    if res.returncode != 0:
        log.info("nmcli not available or scan failed (rc=%s)", res.returncode)
        return []

    networks: list[WifiNetwork] = []
    seen: set[str] = set()
    for line in (res.stdout or "").splitlines():
        # Format: SSID:SIGNAL:SECURITY
        parts = line.split(":")
        if not parts:
            continue
        ssid = parts[0].strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)

        signal: int | None = None
        security: str | None = None
        if len(parts) >= 2 and parts[1].isdigit():
            signal = int(parts[1])
        if len(parts) >= 3:
            security = parts[2].strip() or None

        networks.append(WifiNetwork(ssid=ssid, signal=signal, security=security))

    # Sort by signal desc when present, else alphabetical
    networks.sort(key=lambda n: (-(n.signal or 0), n.ssid.casefold()))
    return networks
