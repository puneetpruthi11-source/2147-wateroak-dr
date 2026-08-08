"""Orchestrate a single backup pass: mount phone -> scan -> upload new files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import device
from .config import Config, ensure_state_dir
from .graph import OneDriveClient
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
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.device_name}: {self.uploaded} uploaded, {self.skipped} already "
            f"backed up, {self.failed} failed (of {self.scanned} media files)."
        )


def _iter_media_files(root: Path, include_exts: set[str]):
    """Yield (absolute_path, relative_path_str) for backup-eligible files."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith("._") or name == ".DS_Store":
            continue  # macOS/AppleDouble junk
        if path.suffix.lower() not in include_exts:
            continue
        yield path, str(path.relative_to(root))


def backup_device(cfg: Config, udid: str, client: OneDriveClient,
                  manifest: Manifest) -> BackupResult:
    """Back up one connected device. Assumes it is paired and ready."""
    result = BackupResult(device_name=device.device_name(udid))
    include_exts = {e.lower() for e in cfg.include_extensions}

    with device.mounted_media(udid, cfg.mount_path) as mount:
        source_root = mount / cfg.source_subdir
        if not source_root.exists():
            # Some layouts expose DCIM directly at the mount root.
            source_root = mount
        log.info("Scanning %s", source_root)

        for abs_path, rel in _iter_media_files(source_root, include_exts):
            result.scanned += 1
            try:
                st = abs_path.stat()
            except OSError as e:
                result.failed += 1
                result.errors.append(f"{rel}: stat failed: {e}")
                continue

            if manifest.is_uploaded(rel, st.st_size, st.st_mtime_ns):
                result.skipped += 1
                continue

            captured = datetime.fromtimestamp(st.st_mtime)
            remote_rel = remote_relative_path(rel, captured, cfg.organize_by)
            remote_path = full_remote_path(cfg.remote_base_folder, remote_rel)

            try:
                client.upload_file(abs_path, remote_path)
                manifest.mark_done(rel, st.st_size, st.st_mtime_ns, remote_path)
                result.uploaded += 1
                log.info("Uploaded %s -> %s", rel, remote_path)
            except Exception as e:  # noqa: BLE001 - record and keep going
                manifest.mark_failed(rel, st.st_size, st.st_mtime_ns, str(e))
                result.failed += 1
                result.errors.append(f"{rel}: {e}")
                log.warning("Failed %s: %s", rel, e)

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

    client = OneDriveClient(
        client_id=cfg.client_id,
        tenant=cfg.tenant,
        token_cache_path=cfg.token_cache_path,
        chunk_size_bytes=cfg.chunk_size_bytes,
    )

    with manifest_for(cfg) as manifest:
        return backup_device(cfg, udid, client, manifest)


def manifest_for(cfg: Config) -> Manifest:
    return Manifest(cfg.manifest_path)
