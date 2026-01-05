from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from vistula_installer.core.executor import CommandExecutor


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlatpakApp:
    appid: str
    name: str
    description: str


_SPLIT_RE = re.compile(r"\s{2,}")


def search_flatpak(executor: CommandExecutor, query: str, *, limit: int = 25) -> list[FlatpakApp]:
    """Best-effort Flatpak search.

    Uses `flatpak search` when available. Output format differs between versions,
    so parsing is intentionally tolerant.
    """
    q = (query or "").strip()
    if not q:
        return []

    res = executor.run(
        [
            "flatpak",
            "search",
            "--columns=application,name,description",
            q,
        ],
        check=False,
        allow_in_dry_run=True,
    )

    if res.returncode != 0:
        log.info("flatpak search failed (rc=%s)", res.returncode)
        return []

    apps: list[FlatpakApp] = []
    for raw in (res.stdout or "").splitlines():
        line = raw.strip("\n")
        if not line.strip():
            continue
        # Skip header if present
        if "Application" in line and "Description" in line:
            continue

        # Prefer tab split, fallback to 2+ spaces
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        else:
            parts = [p.strip() for p in _SPLIT_RE.split(line) if p.strip()]

        if len(parts) < 2:
            continue
        appid = parts[0]
        name = parts[1] if len(parts) >= 2 else appid
        desc = parts[2] if len(parts) >= 3 else ""

        if "/" in appid or " " in appid:
            # Sometimes output includes extra columns or malformed entries.
            continue
        if not appid:
            continue

        apps.append(FlatpakApp(appid=appid, name=name, description=desc))
        if len(apps) >= limit:
            break

    return apps
