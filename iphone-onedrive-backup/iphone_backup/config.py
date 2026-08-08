"""Configuration loading and default paths.

Config lives at ~/.config/iphone-onedrive-backup/config.json by default.
State (token cache, manifest DB, logs, mount point) lives alongside it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path


APP_DIR_NAME = "iphone-onedrive-backup"


def default_state_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_DIR_NAME


@dataclass
class Config:
    # Which OneDrive upload engine to use:
    #   "rclone" -> upload via the `rclone` CLI (recommended). No Azure app
    #               registration needed; rclone ships its own OAuth client and
    #               you sign in once with `iphone-backup login`.
    #   "graph"  -> use the built-in Microsoft Graph uploader (needs your own
    #               Azure "Application (client) ID" below).
    backend: str = "rclone"

    # Name of the configured rclone remote pointing at your OneDrive
    # (used when backend == "rclone").
    rclone_remote: str = "onedrive"

    # Azure "Application (client) ID" — only needed when backend == "graph".
    # This is a public-client desktop app, so no client secret is needed.
    client_id: str = ""

    # "consumers" = personal Microsoft accounts (outlook.com/hotmail/live).
    # "organizations" = work/school. "common" = both.  (graph backend only)
    tenant: str = "consumers"

    # Top-level OneDrive folder that everything is uploaded under.
    remote_base_folder: str = "iPhone Backup"

    # How to lay out files inside remote_base_folder:
    #   "date" -> YYYY/MM/filename       (recommended)
    #   "dcim" -> mirror the phone's DCIM folder structure
    #   "flat" -> everything directly in the base folder
    organize_by: str = "date"

    # Which folder on the phone to read. "DCIM" holds the camera roll.
    source_subdir: str = "DCIM"

    # Upload chunk size for large files, in MiB. Must be a multiple of 0.3125
    # (320 KiB) per the Graph API; whole numbers of MiB are always valid.
    chunk_size_mib: int = 10

    # How often the watcher polls for a connected phone, in seconds.
    poll_interval_seconds: int = 5

    # File extensions to back up (lowercase, with dot).
    include_extensions: list[str] = field(default_factory=lambda: [
        ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tiff", ".dng",
        ".mov", ".mp4", ".m4v", ".avi",
    ])

    # Where the phone gets mounted and where state is kept. Filled in on load.
    state_dir: str = ""
    mount_point: str = ""

    @property
    def state_path(self) -> Path:
        return Path(self.state_dir)

    @property
    def token_cache_path(self) -> Path:
        return self.state_path / "token_cache.bin"

    @property
    def manifest_path(self) -> Path:
        return self.state_path / "manifest.db"

    @property
    def log_path(self) -> Path:
        return self.state_path / "backup.log"

    @property
    def mount_path(self) -> Path:
        return Path(self.mount_point)

    @property
    def chunk_size_bytes(self) -> int:
        return int(self.chunk_size_mib) * 1024 * 1024


def config_file_path(state_dir: Path | None = None) -> Path:
    sd = state_dir or default_state_dir()
    return sd / "config.json"


def load_config(state_dir: Path | None = None) -> Config:
    """Load config from disk, filling in default paths. Missing file => defaults."""
    sd = state_dir or default_state_dir()
    cfg_path = config_file_path(sd)

    data: dict = {}
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text())

    cfg = Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})

    if not cfg.state_dir:
        cfg.state_dir = str(sd)
    if not cfg.mount_point:
        cfg.mount_point = str(Path(cfg.state_dir) / "mnt")
    return cfg


def save_config(cfg: Config) -> Path:
    sd = Path(cfg.state_dir) if cfg.state_dir else default_state_dir()
    sd.mkdir(parents=True, exist_ok=True)
    path = config_file_path(sd)
    path.write_text(json.dumps(asdict(cfg), indent=2))
    return path


def ensure_state_dir(cfg: Config) -> None:
    cfg.state_path.mkdir(parents=True, exist_ok=True)
    cfg.mount_path.mkdir(parents=True, exist_ok=True)
