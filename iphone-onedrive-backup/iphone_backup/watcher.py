"""Watch for a connected iPhone and back it up automatically.

Runs as a long-lived loop (typically under launchd). It polls for connected
devices; when a device newly appears, it runs a backup. A device must
disconnect and reconnect to trigger another automatic run, so leaving the
phone plugged in does not loop forever.
"""

from __future__ import annotations

import logging
import time

from . import device
from .config import Config
from .backup import run_backup

log = logging.getLogger("iphone_backup")


def watch(cfg: Config, run_once_if_connected: bool = True) -> None:
    """Poll indefinitely, backing up each device as it connects."""
    log.info("Watcher started (polling every %ss). Waiting for an iPhone…",
             cfg.poll_interval_seconds)

    active: set[str] = set()

    # Optionally skip auto-backing-up a device that's already plugged in at
    # startup, so restarting the watcher doesn't re-scan an idle phone.
    if not run_once_if_connected:
        active = set(device.list_connected_udids())

    while True:
        try:
            connected = set(device.list_connected_udids())
        except device.DeviceError as e:
            log.warning("Could not list devices: %s", e)
            connected = set()

        newly = connected - active
        for udid in newly:
            _backup_one(cfg, udid)

        # Drop devices that went away so a reconnect fires a fresh backup.
        active = connected

        time.sleep(max(1, cfg.poll_interval_seconds))


def _backup_one(cfg: Config, udid: str) -> None:
    try:
        name = device.device_name(udid)
        log.info("Detected %s (%s). Starting backup…", name, udid)
        result = run_backup(cfg, udid=udid)
        log.info("Backup complete — %s", result.summary())
        for err in result.errors[:20]:
            log.warning("  • %s", err)
    except Exception as e:  # noqa: BLE001 - watcher must survive any failure
        log.error("Backup for %s failed: %s", udid, e)
