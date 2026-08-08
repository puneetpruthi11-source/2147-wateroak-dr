"""Command-line interface.

    iphone-backup init      # create config, ask for your Azure client ID
    iphone-backup login     # sign in to OneDrive (one time)
    iphone-backup doctor    # check tools, device, and OneDrive connection
    iphone-backup backup    # back up the connected phone once, now
    iphone-backup watch     # run forever, backing up on every connect
    iphone-backup status    # show how many files have been backed up
    iphone-backup install-agent    # install the auto-start background service
    iphone-backup reset     # forget upload history (re-uploads everything)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

from . import __version__, device
from .backup import manifest_for, run_backup
from .config import Config, ensure_state_dir, load_config, save_config
from .logging_setup import setup_logging
from .watcher import watch


def _load(args) -> Config:
    state_dir = Path(args.state_dir) if args.state_dir else None
    return load_config(state_dir)


def cmd_init(args) -> int:
    cfg = _load(args)
    print("Setting up iPhone → OneDrive backup.\n")

    backend = input(
        f"Upload backend [{cfg.backend}] "
        "(rclone = no Azure needed, graph = your own Azure app): "
    ).strip().lower()
    if backend in ("rclone", "graph"):
        cfg.backend = backend

    if cfg.backend == "rclone":
        remote = input(f"rclone remote name [{cfg.rclone_remote}]: ").strip()
        if remote:
            cfg.rclone_remote = remote
    else:
        client_id = input(f"Azure app (client) ID [{cfg.client_id or 'see README'}]: ").strip()
        if client_id:
            cfg.client_id = client_id
        tenant = input(f"Account type [{cfg.tenant}] "
                       "(consumers=personal, organizations=work, common=both): ").strip()
        if tenant:
            cfg.tenant = tenant

    base = input(f"OneDrive folder [{cfg.remote_base_folder}]: ").strip()
    if base:
        cfg.remote_base_folder = base

    ensure_state_dir(cfg)
    path = save_config(cfg)
    print(f"\nSaved config to {path}")
    print("Next: run `iphone-backup login` to connect OneDrive.")
    return 0


def cmd_login(args) -> int:
    cfg = _load(args)
    ensure_state_dir(cfg)
    if cfg.backend == "rclone":
        return _login_rclone(cfg)

    from .graph import OneDriveClient
    client = OneDriveClient(cfg.client_id, cfg.tenant, cfg.token_cache_path)
    client.sign_in()
    me = client.whoami()
    who = me.get("userPrincipalName") or me.get("displayName") or "your account"
    print(f"Signed in as {who}. Token cached at {cfg.token_cache_path}")
    return 0


def _login_rclone(cfg: Config) -> int:
    from .rclone_backend import RcloneClient, RcloneError, rclone_available

    if not rclone_available():
        print("rclone isn't installed yet. Install it first:\n\n    brew install rclone\n")
        return 1

    print(textwrap.dedent(f"""
        Launching `rclone config` to connect your OneDrive. Answer like this:

          n)  New remote
          name>            {cfg.rclone_remote}
          Storage>         onedrive        (type it, or pick "Microsoft OneDrive")
          client_id>       (leave blank — press Enter)
          client_secret>   (leave blank — press Enter)
          region>          1               (Microsoft Cloud Global)
          Edit advanced config?   n
          Use web browser to automatically authenticate?   y
            -> your browser opens; sign in as your hotmail account and Accept
          Your choice>     1               (OneDrive Personal or Business)
          Chosen drive is correct?   y
          Keep this "{cfg.rclone_remote}" remote?   y
          q)  Quit config

        (Nothing here touches Azure — rclone uses its own sign-in.)
    """).strip() + "\n")

    try:
        input("Press Enter to launch `rclone config` (Ctrl-C to cancel)… ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1

    subprocess.run(["rclone", "config"])

    try:
        client = RcloneClient(cfg.rclone_remote)
        if client.remote_exists():
            print(f"\n✓ rclone remote '{cfg.rclone_remote}' is configured.")
            try:
                print(client.about())
            except RcloneError:
                pass
            print("You're ready — run `iphone-backup doctor` to confirm everything.")
            return 0
        print(f"\n⚠ Didn't find a remote named '{cfg.rclone_remote}'. If you named it "
              "something else, update it with:\n"
              f"    iphone-backup init\n(or re-run `iphone-backup login`).")
        return 1
    except RcloneError as e:
        print(f"\n✗ {e}")
        return 1


def cmd_doctor(args) -> int:
    cfg = _load(args)
    ok = True

    missing = device.check_tools()
    if missing:
        ok = False
        print("✗ Missing tools:", ", ".join(missing))
        print("  Fix: pip install pymobiledevice3  (usually installed with this app)")
    else:
        print("✓ pymobiledevice3 found")

    try:
        udids = device.list_connected_udids()
        if udids:
            for u in udids:
                print(f"✓ Device connected: {device.device_name(u)}")
                print("  (unlock it and tap 'Trust This Computer' if prompted)")
        else:
            print("… No iPhone connected right now (connect one to back up)")
    except device.DeviceError as e:
        ok = False
        print(f"✗ Device check failed: {e}")

    if cfg.backend == "rclone":
        from .rclone_backend import RcloneClient, RcloneError, rclone_available
        if not rclone_available():
            ok = False
            print("✗ rclone not installed — brew install rclone")
        else:
            try:
                client = RcloneClient(cfg.rclone_remote)
                if client.remote_exists():
                    client.about()  # verifies the token actually works
                    print(f"✓ rclone remote '{cfg.rclone_remote}' connected to OneDrive")
                else:
                    ok = False
                    print(f"✗ rclone remote '{cfg.rclone_remote}' not found — "
                          "run `iphone-backup login`")
            except RcloneError as e:
                ok = False
                print(f"✗ OneDrive (rclone) check failed: {e}")
    else:
        from .graph import AuthError, OneDriveClient
        if not cfg.client_id:
            ok = False
            print("✗ No Azure client_id set — run `iphone-backup init`")
        else:
            try:
                client = OneDriveClient(cfg.client_id, cfg.tenant, cfg.token_cache_path)
                me = client.whoami()
                print(f"✓ OneDrive signed in as "
                      f"{me.get('userPrincipalName') or me.get('displayName')}")
            except AuthError:
                ok = False
                print("✗ Not signed in to OneDrive — run `iphone-backup login`")
            except Exception as e:  # noqa: BLE001
                print(f"… OneDrive check inconclusive: {e}")

    print("\nAll good." if ok else "\nSome checks failed — see above.")
    return 0 if ok else 1


def cmd_backup(args) -> int:
    cfg = _load(args)
    result = run_backup(cfg, udid=args.udid)
    print(result.summary())
    for err in result.errors[:20]:
        print("  •", err)
    if len(result.errors) > 20:
        print(f"  … and {len(result.errors) - 20} more (see {cfg.log_path})")
    return 0 if result.failed == 0 else 2


def cmd_watch(args) -> int:
    cfg = _load(args)
    ensure_state_dir(cfg)
    watch(cfg, run_once_if_connected=not args.skip_current)
    return 0


def cmd_status(args) -> int:
    cfg = _load(args)
    with manifest_for(cfg) as m:
        c = m.counts()
    print(f"Backed up: {c['done']} files")
    print(f"Failed:    {c['failed']} files")
    print(f"Manifest:  {cfg.manifest_path}")
    print(f"Logs:      {cfg.log_path}")
    return 0


def cmd_reset(args) -> int:
    cfg = _load(args)
    if not args.yes:
        ans = input("This forgets all upload history; the next backup re-uploads "
                    "everything. Continue? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return 1
    with manifest_for(cfg) as m:
        m.clear()
    print("Upload history cleared.")
    return 0


def cmd_install_agent(args) -> int:
    from .installer import install_agent
    cfg = _load(args)
    ensure_state_dir(cfg)
    plist_path = install_agent(cfg, python_executable=sys.executable)
    print(f"Installed and loaded launchd agent: {plist_path}")
    print("It will now back up your iPhone automatically whenever you connect it.")
    print(f"Logs: {cfg.log_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="iphone-backup",
        description="Back up iPhone photos/videos to OneDrive over USB (macOS).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--state-dir", help="Override config/state directory")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create config and set your Azure client ID").set_defaults(func=cmd_init)
    sub.add_parser("login", help="Sign in to OneDrive").set_defaults(func=cmd_login)
    sub.add_parser("doctor", help="Check tools, device, and OneDrive").set_defaults(func=cmd_doctor)

    b = sub.add_parser("backup", help="Back up the connected phone once")
    b.add_argument("--udid", help="Target a specific device UDID")
    b.set_defaults(func=cmd_backup)

    w = sub.add_parser("watch", help="Run forever; back up on every connect")
    w.add_argument("--skip-current", action="store_true",
                   help="Don't back up a device already connected at startup")
    w.set_defaults(func=cmd_watch)

    sub.add_parser("status", help="Show backup counts").set_defaults(func=cmd_status)
    sub.add_parser("install-agent", help="Install auto-start background service").set_defaults(func=cmd_install_agent)

    r = sub.add_parser("reset", help="Forget upload history")
    r.add_argument("-y", "--yes", action="store_true", help="Don't prompt")
    r.set_defaults(func=cmd_reset)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = _load(args)
    setup_logging(cfg.log_path if cfg.state_dir else None, verbose=args.verbose)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except RuntimeError as e:
        # DeviceError, AuthError, UploadError, RcloneError all derive from this.
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
