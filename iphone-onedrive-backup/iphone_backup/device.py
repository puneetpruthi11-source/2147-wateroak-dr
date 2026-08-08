"""Talk to a USB-connected iPhone on macOS via libimobiledevice + ifuse.

Requires (install with Homebrew):
    brew install libimobiledevice ifuse
    # ifuse also needs macFUSE: https://osxfuse.github.io  (one-time approval
    # in System Settings -> Privacy & Security after install)

Nothing here is Apple-private: libimobiledevice speaks the same USB protocol
iTunes/Finder uses, and ifuse exposes the phone's media area (which contains
DCIM) as a normal folder we can copy from.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path


class DeviceError(RuntimeError):
    pass


REQUIRED_TOOLS = ["idevice_id", "ideviceinfo", "idevicepair", "ifuse"]


def check_tools() -> list[str]:
    """Return the list of required CLI tools that are missing from PATH."""
    return [t for t in REQUIRED_TOOLS if shutil.which(t) is None]


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as e:
        raise DeviceError(f"Required tool not found: {cmd[0]}. Run: brew install libimobiledevice ifuse") from e
    except subprocess.TimeoutExpired as e:
        raise DeviceError(f"Command timed out: {' '.join(cmd)}") from e


def list_connected_udids() -> list[str]:
    """UDIDs of iPhones/iPads currently connected over USB (empty if none)."""
    proc = _run(["idevice_id", "-l"])
    if proc.returncode != 0:
        # No device or usbmuxd not running -> treat as "none connected".
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def device_name(udid: str) -> str:
    proc = _run(["ideviceinfo", "-u", udid, "-k", "DeviceName"])
    name = proc.stdout.strip()
    return name or udid


def is_paired(udid: str) -> bool:
    proc = _run(["idevicepair", "-u", udid, "validate"])
    return proc.returncode == 0


def pair(udid: str) -> None:
    """Attempt to pair. The user must tap 'Trust' on an unlocked phone."""
    proc = _run(["idevicepair", "-u", udid, "pair"], timeout=60)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        raise DeviceError(
            f"Pairing failed for {udid}: {msg}\n"
            "Unlock the iPhone and tap 'Trust This Computer', then retry."
        )


def wait_until_ready(udid: str, timeout: int = 60, interval: float = 2.0) -> None:
    """Block until the device is paired and reachable, pairing if needed."""
    deadline = time.monotonic() + timeout
    last_err = ""
    while time.monotonic() < deadline:
        if udid not in list_connected_udids():
            last_err = "device disconnected"
        elif is_paired(udid):
            return
        else:
            try:
                pair(udid)
                if is_paired(udid):
                    return
            except DeviceError as e:
                last_err = str(e)
        time.sleep(interval)
    raise DeviceError(f"Device {udid} not ready after {timeout}s: {last_err}")


@contextmanager
def mounted_media(udid: str, mount_point: Path):
    """Mount the iPhone's media area at mount_point for the duration of the block.

    Yields the Path to the mount. The camera roll is at <mount>/DCIM.
    Always unmounts on exit, even on error.
    """
    mount_point = Path(mount_point)
    mount_point.mkdir(parents=True, exist_ok=True)

    # Clean up a stale mount if one is lingering.
    _unmount(mount_point)

    proc = _run(["ifuse", "--udid", udid, str(mount_point)], timeout=60)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        raise DeviceError(
            f"ifuse mount failed: {msg}\n"
            "Make sure macFUSE is installed and approved in "
            "System Settings -> Privacy & Security, and the phone is unlocked."
        )

    # Give the FUSE mount a moment to become readable.
    for _ in range(10):
        if (mount_point / "DCIM").exists() or any(mount_point.iterdir()):
            break
        time.sleep(0.5)

    try:
        yield mount_point
    finally:
        _unmount(mount_point)


def _unmount(mount_point: Path) -> None:
    # macOS uses `umount`; `diskutil unmount` is a fallback for FUSE volumes.
    for cmd in (["umount", str(mount_point)], ["diskutil", "unmount", str(mount_point)]):
        proc = _run(cmd, timeout=30)
        if proc.returncode == 0:
            return
