"""Upload to OneDrive via the `rclone` CLI.

Why rclone: it ships its own OAuth client registration, so you do NOT need to
register an Azure app. You authorize it once in your browser (`rclone config`,
driven by `iphone-backup login`) and it stores a refresh token in its own
config file. This module just shells out to `rclone copyto` for each new file,
which keeps our per-file manifest and date-based organization intact.

Install: brew install rclone   (https://rclone.org)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class RcloneError(RuntimeError):
    pass


def rclone_available() -> bool:
    return shutil.which("rclone") is not None


def build_copyto_args(remote: str, remote_path: str, local_path: str,
                      config_path: str | None = None,
                      extra_args: list[str] | None = None) -> list[str]:
    """Build the `rclone copyto` argv for uploading one file.

    Pure/side-effect-free so it can be unit-tested. `copyto` (not `copy`)
    targets an exact destination *path*, which is what our computed
    year/month/filename layout needs. rclone creates parent folders as needed.
    """
    args = ["rclone", "copyto"]
    if config_path:
        args += ["--config", config_path]
    if extra_args:
        args += list(extra_args)
    args += [local_path, f"{remote}:{remote_path}"]
    return args


class RcloneClient:
    """Duck-types the OneDriveClient interface used by backup.py (`upload_file`)."""

    def __init__(self, remote: str, config_path: str | None = None,
                 extra_args: list[str] | None = None):
        if not rclone_available():
            raise RcloneError(
                "rclone is not installed. Install it with: brew install rclone"
            )
        if not remote:
            raise RcloneError("No rclone remote configured (see config.rclone_remote).")
        self.remote = remote
        self.config_path = config_path
        # Sensible defaults: don't spam progress, but surface real errors.
        self.extra_args = extra_args if extra_args is not None else [
            "--onedrive-chunk-size", "10M",
        ]

    def _run(self, args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(args, capture_output=True, text=True,
                                  timeout=timeout, check=False)
        except FileNotFoundError as e:
            raise RcloneError("rclone binary not found. Install: brew install rclone") from e
        except subprocess.TimeoutExpired as e:
            raise RcloneError(f"rclone timed out: {' '.join(args)}") from e

    def remote_exists(self) -> bool:
        args = ["rclone", "listremotes"]
        if self.config_path:
            args += ["--config", self.config_path]
        proc = self._run(args, timeout=30)
        if proc.returncode != 0:
            return False
        remotes = {line.strip().rstrip(":") for line in proc.stdout.splitlines()}
        return self.remote in remotes

    def about(self) -> str:
        """Human-readable account/quota summary; also verifies auth works."""
        args = ["rclone", "about", f"{self.remote}:"]
        if self.config_path:
            args += ["--config", self.config_path]
        proc = self._run(args, timeout=60)
        if proc.returncode != 0:
            raise RcloneError((proc.stderr or proc.stdout).strip() or "rclone about failed")
        return proc.stdout.strip()

    def upload_file(self, local_path: Path, remote_path: str) -> dict:
        args = build_copyto_args(
            self.remote, remote_path, str(local_path),
            config_path=self.config_path, extra_args=self.extra_args,
        )
        proc = self._run(args, timeout=3600)  # allow big videos
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout).strip()
            raise RcloneError(f"rclone upload failed: {msg[:500]}")
        return {"remote": f"{self.remote}:{remote_path}"}
