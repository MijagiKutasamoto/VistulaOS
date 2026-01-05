from __future__ import annotations

import argparse
import os
import sys

from vistula_installer.core.config import AppConfig
from vistula_installer.core.logging import setup_logging
from vistula_installer.ui.gtk_wizard import run_gui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vistula-installer")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not perform destructive actions; log what would be executed.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Override log file path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = AppConfig.load()
    config.runtime.dry_run = bool(args.dry_run)

    log_file = args.log_file or config.paths.log_file
    setup_logging(debug=bool(args.debug), log_file=log_file)

    # GTK apps should not be run as setuid; require explicit root only for install.
    if os.geteuid() == 0 and os.environ.get("SUDO_USER") is None:
        # Being root is fine in a live environment, but we keep UI safe anyway.
        pass

    return run_gui(config=config)


if __name__ == "__main__":
    raise SystemExit(main())
