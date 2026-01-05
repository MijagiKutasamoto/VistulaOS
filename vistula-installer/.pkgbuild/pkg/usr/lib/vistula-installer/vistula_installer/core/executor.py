from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandExecutor:
    def __init__(self, *, dry_run: bool) -> None:
        self._dry_run = dry_run

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def run(
        self,
        args: list[str],
        *,
        check: bool = True,
        cwd: str | None = None,
        allow_in_dry_run: bool = False,
        input_text: str | None = None,
    ) -> CommandResult:
        cmd = " ".join(shlex.quote(a) for a in args)
        if self._dry_run and not allow_in_dry_run:
            log.info("[DRY-RUN] %s", cmd)
            return CommandResult(returncode=0, stdout="", stderr="")

        log.info("$ %s", cmd)
        cp = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            input=input_text,
            capture_output=True,
        )
        if check and cp.returncode != 0:
            log.error("Command failed (%s): %s\nSTDOUT:\n%s\nSTDERR:\n%s", cp.returncode, cmd, cp.stdout, cp.stderr)
            raise RuntimeError(f"Command failed ({cp.returncode}): {cmd}")
        return CommandResult(returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)
