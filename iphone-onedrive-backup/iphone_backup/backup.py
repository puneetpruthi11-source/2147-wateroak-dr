"""Orchestrate a single backup pass: list phone media -> pull new -> upload."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import device
from .config import Config, ensure_state_dir
from .manifest import Manifest
from .remote_paths import full_remote_path, remote_relative_path

log = logging.getLogger("iphone_backup")


@dataclass
class BackupResult:
    device_name: str = ""
    scanned: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    disconnected: bool = False
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        base = (
            f"{self.device_name}: {self.uploaded} uploaded, {self.skipped} already "
            f"backed up, {self.failed} failed (of {self.scanned} media files)."
        )
        if self.disconnected:
            base += " Stopped early — iPhone disconnected; reconnect to resume."
        return base


def backup_device(cfg: Config, udid: str, client, manifest: Manifest) -> BackupResult:
    """Back up one connected device. Assumes it is unlocked, trusted, and ready.

    Flow: list the phone's media paths (cheap), skip ones already uploaded, and
    for each new file: copy it off the phone to a temp file, upload it, record
    it, delete the temp. Only new files ever cross the USB cable or the network.
    """
    result = BackupResult(device_name=device.device_name(udid))
    include_exts = {e.lower() for e in cfg.include_extensions}

    paths = device.list_media_paths(udid, cfg.source_subdir, include_exts)
    result.scanned = len(paths)
    log.info("%s: %d media files on device", result.device_name, len(paths))

    with tempfile.TemporaryDirectory(prefix="iphone-backup-") as tmp:
        tmpdir = Path(tmp)
        for remote_src in paths:
            if manifest.has_done(remote_src):
                result.skipped += 1
                continue

            local = tmpdir / remote_src.rsplit("/", 1)[-1]
            try:
                device.pull_file(udid, remote_src, local)
                st = local.stat()
                captured = datetime.fromtimestamp(st.st_mtime)
                remote_rel = remote_relative_path(remote_src, captured, cfg.organize_by)
                remote_path = full_remote_path(cfg.remote_base_folder, remote_rel)

                client.upload_file(local, remote_path)
                manifest.mark_done(remote_src, st.st_size, st.st_mtime_ns, remote_path)
                result.uploaded += 1
                log.info("Uploaded %s -> %s", remote_src, remote_path)
            except Exception as e:  # noqa: BLE001 - record and keep going
                # If the phone dropped off USB, stop now instead of failing every
                # remaining file the same way. Nothing uploaded so far is lost.
                if device.is_disconnect_error(str(e)):
                    result.disconnected = True
                    result.errors.append("iPhone disconnected — stopped; reconnect to resume.")
                    log.warning("iPhone disconnected mid-backup; stopping. Reconnect to resume.")
                    break
                manifest.mark_failed(remote_src, 0, 0, str(e))
                result.failed += 1
                result.errors.append(f"{remote_src}: {e}")
                log.warning("Failed %s: %s", remote_src, e)
            finally:
                if local.exists():
                    try:
                        local.unlink()
                    except OSError:
                        pass

    return result


def run_backup(cfg: Config, udid: str | None = None) -> BackupResult:
    """Top-level entry: prepare state, pick a device, and back it up."""
    ensure_state_dir(cfg)

    missing = device.check_tools()
    if missing:
        raise device.DeviceError(
            "Missing required tools: " + ", ".join(missing) +
            "\nInstall with: brew install libimobiledevice ifuse"
        )

    if udid is None:
        udids = device.list_connected_udids()
        if not udids:
            raise device.DeviceError("No iPhone/iPad is connected over USB.")
        udid = udids[0]

    device.wait_until_ready(udid)

    client = make_client(cfg)

    with manifest_for(cfg) as manifest:
        return backup_device(cfg, udid, client, manifest)


def make_client(cfg: Config):
    """Construct the upload client for the configured backend."""
    if cfg.backend == "rclone":
        from .rclone_backend import RcloneClient
        return RcloneClient(cfg.rclone_remote)
    if cfg.backend == "graph":
        from .graph import OneDriveClient
        return OneDriveClient(
            client_id=cfg.client_id,
            tenant=cfg.tenant,
            token_cache_path=cfg.token_cache_path,
            chunk_size_bytes=cfg.chunk_size_bytes,
        )
    raise ValueError(f"Unknown backend: {cfg.backend!r} (use 'rclone' or 'graph')")


def manifest_for(cfg: Config) -> Manifest:
    return Manifest(cfg.manifest_path)
