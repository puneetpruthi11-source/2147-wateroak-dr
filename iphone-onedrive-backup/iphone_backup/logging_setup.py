"""Logging configuration shared by the CLI and the launchd watcher."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_path: Path | None = None, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if called twice.
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        fileh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3)
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
