"""Talk to a USB-connected iPhone on macOS via pymobiledevice3.

pymobiledevice3 is a pure-Python implementation of Apple's device protocols.
It talks to the usbmuxd daemon that ships built into macOS, so there is **no
kernel extension, no macFUSE, and no libimobiledevice** to install — it comes
in as a normal pip dependency of this package.

We drive its command-line interface (stable across versions) rather than its
Python API (which is async and changes more often). The camera roll lives under
the AFC media root at ``DCIM``.

Install (handled automatically by `pip install -e .`):
    pip install pymobiledevice3
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path


class DeviceError(RuntimeError):
    pass


PMD = "pymobiledevice3"
REQUIRED_TOOLS = [PMD]

# iPhone UDIDs are either 40 hex chars (legacy) or 8hex-16hex (modern).
_UDID_RE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}|[0-9a-f]{40}")

_TRUST_HINTS = (
    "pair", "trust", "lockdown", "passwordprotected", "not paired",
    "invalidhostid", "sessioninactive", "please enter", "locked",
)


def check_tools() -> list[str]:
    """Return the required CLI tools missing from PATH (empty means all present)."""
    return [t for t in REQUIRED_TOOLS if shutil.which(t) is None]


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise DeviceError(
            f"'{args[0]}' not found. Install it with: pip install pymobiledevice3"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise DeviceError(f"Command timed out: {' '.join(args)}") from e


def _looks_like_trust_error(msg: str) -> bool:
    m = msg.lower()
    return any(h in m for h in _TRUST_HINTS)


def list_connected_udids() -> list[str]:
    """UDIDs of iPhones/iPads connected over USB (empty if none / no usbmuxd)."""
    proc = _run([PMD, "usbmux", "list", "--usb", "--simple"], timeout=30)
    out = (proc.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except json.JSONDecodeError:
        pass
    found = _UDID_RE.findall(out)
    if found:
        return found
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def device_name(udid: str) -> str:
    """Best-effort friendly name for a device; falls back to the UDID."""
    try:
        proc = _run([PMD, "usbmux", "list", "--usb"], timeout=30)
        data = json.loads(proc.stdout)
        norm = udid.replace("-", "")
        for d in data if isinstance(data, list) else []:
            if not isinstance(d, dict):
                continue
            if norm in json.dumps(d).replace("-", ""):
                for k in ("DeviceName", "Name", "name"):
                    if d.get(k):
                        return str(d[k])
    except Exception:  # noqa: BLE001 - name is cosmetic
        pass
    return udid


def wait_until_ready(udid: str, timeout: int = 120, interval: float = 3.0) -> None:
    """Block until the device answers AFC (implies paired + unlocked + trusted).

    Raises a clear, actionable DeviceError if the phone needs to be trusted.
    """
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if udid not in list_connected_udids():
            last = "device disconnected"
        else:
            proc = _run([PMD, "afc", "ls", "DCIM", "--udid", udid], timeout=30)
            if proc.returncode == 0:
                return
            last = (proc.stderr or proc.stdout).strip()
            if _looks_like_trust_error(last):
                raise DeviceError(
                    "The iPhone is locked or hasn't trusted this Mac. Unlock it, tap "
                    "'Trust This Computer' (enter your passcode), then reconnect."
                )
        time.sleep(interval)
    raise DeviceError(f"Device {udid} not ready after {timeout}s: {last}")


def list_media_paths(udid: str, subdir: str, include_exts) -> list[str]:
    """Return device paths of backup-eligible media files under ``subdir``.

    Paths are rooted at the AFC media root (e.g. ``DCIM/100APPLE/IMG_0001.HEIC``)
    and can be passed straight back to :func:`pull_file`.
    """
    proc = _run([PMD, "afc", "ls", "-r", subdir, "--udid", udid], timeout=900)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        if _looks_like_trust_error(msg):
            raise DeviceError(
                "The iPhone is locked or hasn't trusted this Mac. Unlock it and tap "
                "'Trust This Computer', then retry."
            )
        raise DeviceError(f"Could not list photos on the device: {msg[:300]}")

    exts = {e.lower() for e in include_exts}
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        p = line.strip()
        if not p:
            continue
        base = p.rsplit("/", 1)[-1]
        if base.startswith("._") or base == ".DS_Store":
            continue
        dot = base.rfind(".")
        if dot <= 0:
            continue
        if base[dot:].lower() in exts:
            paths.append(p)
    return paths


def pull_file(udid: str, remote_path: str, local_path: Path, timeout: int = 3600) -> None:
    """Copy one file off the device to ``local_path`` (which must not be a dir).

    pymobiledevice3 streams large files in chunks and sets the local mtime to
    match the device, so we can read the capture time from the pulled file.
    """
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(
        [PMD, "afc", "pull", remote_path, str(local_path), "--udid", udid],
        timeout=timeout,
    )
    if proc.returncode != 0 or not local_path.exists():
        msg = (proc.stderr or proc.stdout).strip()
        raise DeviceError(f"Failed to copy {remote_path}: {msg[:300]}")
