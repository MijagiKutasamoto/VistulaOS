from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

try:
    from gi.repository import GLib  # type: ignore
except Exception:  # noqa: BLE001
    GLib = None  # type: ignore


@dataclass(frozen=True)
class CommandResult:
    argv: List[str]
    exit_code: int


def _find_binary(name: str) -> Optional[str]:
    return shutil.which(name)


def have_command(name: str) -> bool:
    return _find_binary(name) is not None


def run_command_async(
    argv: Sequence[str],
    *,
    use_pkexec: bool = False,
    env: Optional[dict] = None,
    on_line: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[CommandResult], None]] = None,
) -> None:
    if not argv:
        raise ValueError("argv is empty")

    cmd = list(argv)
    if use_pkexec:
        cmd = ["pkexec", *cmd]

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    def idle_call(fn: Callable, *args) -> None:
        if fn is None:
            return
        if GLib is None:
            fn(*args)
            return
        GLib.idle_add(fn, *args, priority=GLib.PRIORITY_DEFAULT)

    def emit_line(line: str) -> None:
        if on_line is None:
            return
        idle_call(on_line, line)

    def emit_done(result: CommandResult) -> None:
        if on_done is None:
            return
        idle_call(on_done, result)

    def worker() -> None:
        emit_line(f"$ {' '.join(cmd)}\n")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=merged_env,
            )
        except FileNotFoundError:
            emit_line("Błąd: brak komendy w systemie.\n")
            emit_done(CommandResult(argv=cmd, exit_code=127))
            return
        except Exception as e:  # noqa: BLE001
            emit_line(f"Błąd uruchomienia: {e}\n")
            emit_done(CommandResult(argv=cmd, exit_code=1))
            return

        assert proc.stdout is not None
        for line in proc.stdout:
            emit_line(line)

        exit_code = proc.wait()
        emit_line(f"\n[exit={exit_code}]\n")
        emit_done(CommandResult(argv=cmd, exit_code=exit_code))

    threading.Thread(target=worker, daemon=True).start()
