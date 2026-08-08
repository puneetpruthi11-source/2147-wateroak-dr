"""Install a launchd LaunchAgent so the watcher runs automatically at login.

The agent keeps `iphone-backup watch` alive in the background. Because the
watcher polls for device connections, this is what makes the backup start
"every time you connect your phone" without you doing anything.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config

LABEL = "com.iphonebackup.watcher"


PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>iphone_backup</string>
        <string>--state-dir</string>
        <string>{state_dir}</string>
        <string>watch</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{workdir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>{pythonpath}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout}</string>
    <key>StandardErrorPath</key>
    <string>{stderr}</string>
</dict>
</plist>
"""


def agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist_path() -> Path:
    return agents_dir() / f"{LABEL}.plist"


def render_plist(cfg: Config, python_executable: str, package_parent: Path) -> str:
    return PLIST_TEMPLATE.format(
        label=LABEL,
        python=python_executable,
        state_dir=cfg.state_dir,
        workdir=str(package_parent),
        pythonpath=str(package_parent),
        stdout=str(cfg.state_path / "watcher.out.log"),
        stderr=str(cfg.state_path / "watcher.err.log"),
    )


def install_agent(cfg: Config, python_executable: str) -> Path:
    package_parent = Path(__file__).resolve().parent.parent
    content = render_plist(cfg, python_executable, package_parent)

    agents_dir().mkdir(parents=True, exist_ok=True)
    path = plist_path()
    path.write_text(content)

    # Reload: bootout an old copy (ignore errors), then bootstrap the new one.
    uid = _uid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True, text=True)
    proc = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        # Fall back to the older load syntax on macOS versions that need it.
        subprocess.run(["launchctl", "load", "-w", str(path)],
                       capture_output=True, text=True)
    return path


def uninstall_agent() -> None:
    uid = _uid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True, text=True)
    p = plist_path()
    if p.exists():
        p.unlink()


def _uid() -> int:
    import os
    return os.getuid()
