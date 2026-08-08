# iPhone → OneDrive Photo Backup (macOS)

Automatically copy the photos and videos off your iPhone and upload the new
ones to **Microsoft OneDrive**. Plug your phone into your Mac and the backup
starts on its own — every time, only for photos it hasn't already saved.

- 📷 Reads full-resolution **originals** (HEIC, JPEG, PNG, MOV, MP4, DNG …) over USB
- ☁️ Uploads to OneDrive via **rclone** — no Azure app registration, just one browser sign-in
- 🔁 **Incremental** — a local database remembers what's uploaded, so each run only sends new photos
- ⚡ **Auto-start on connect** — a background agent watches for your phone and fires the backup
- 🗂️ Organizes uploads by capture date (`iPhone Backup/2024/03/IMG_0001.HEIC`)

---

## How it works

macOS doesn't let software read an iPhone's filesystem directly. This tool uses
[`libimobiledevice`](https://libimobiledevice.org/) + `ifuse` — the same open
protocol Finder/iTunes uses — to mount the phone's camera roll (`DCIM`) as a
folder, then walks it and uploads anything new through
[`rclone`](https://rclone.org/), which handles the OneDrive connection.

```
iPhone (USB) → ifuse mount (/DCIM) → scan → skip already-uploaded → rclone → OneDrive
                                                     ▲
                                          local manifest.db (SQLite)
```

A launchd background agent runs `iphone-backup watch`, which polls for a
connected device and runs a backup the moment one appears.

> **Why rclone?** Microsoft no longer lets personal (outlook/hotmail) accounts
> register their own API app without a full Azure/M365 directory. rclone ships
> its own sign-in, so you authorize once in the browser and never touch Azure.
> (A built-in Microsoft Graph backend is still available — see
> [Advanced](#advanced-use-the-built-in-graph-backend-instead) — if you'd rather
> use your own Azure app.)

---

## Requirements

- macOS (Intel or Apple Silicon)
- Python 3.10+
- A Microsoft account with OneDrive
- Homebrew

---

## Setup

### 1. Install the tools

```bash
brew install libimobiledevice ifuse rclone
```

`ifuse` needs **macFUSE**. If `brew install ifuse` doesn't pull it in:

```bash
brew install --cask macfuse
```

Then open **System Settings → Privacy & Security** and click **Allow** for the
macFUSE system extension (you may need to reboot once). This is a one-time step.

### 2. Install this tool

```bash
git clone https://github.com/puneetpruthi11-source/iphone-onedrive-backup.git
cd iphone-onedrive-backup
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # installs deps and the `iphone-backup` command
```

### 3. Configure and connect OneDrive

```bash
iphone-backup init      # press Enter to accept the rclone defaults
iphone-backup login     # launches `rclone config` to sign in to OneDrive
```

During `login`, `rclone config` asks a series of questions. The answers:

| Prompt | Answer |
|---|---|
| `n/s/q>` | `n` (new remote) |
| name | `onedrive` |
| Storage | `onedrive` (or pick *Microsoft OneDrive*) |
| client_id | *(blank — press Enter)* |
| client_secret | *(blank — press Enter)* |
| region | `1` (Microsoft Cloud Global) |
| Edit advanced config? | `n` |
| Use web browser to authenticate? | `y` — sign in as your Microsoft account, click **Accept** |
| Your choice (drive type) | `1` (OneDrive Personal or Business) |
| Chosen drive is correct? | `y` |
| Keep this remote? | `y` |
| final menu | `q` (quit) |

`iphone-backup login` prints this same cheat-sheet before launching.

### 4. Check everything

```bash
iphone-backup doctor
```

You want all ✓: tools installed, device connected + paired (unlock the phone and
tap **Trust This Computer** the first time), and OneDrive reachable via rclone.

---

## Usage

### Back up now (manual)

```bash
iphone-backup backup
```

### Turn on automatic backup-on-connect

```bash
iphone-backup install-agent
```

This installs a launchd agent (`~/Library/LaunchAgents/com.iphonebackup.watcher.plist`)
that runs in the background at login. From now on, **just plug in your iPhone**
and new photos upload automatically. A phone must be unplugged and replugged to
trigger the next automatic run, so it won't loop while it sits on the charger.

Watch it work:

```bash
tail -f "$HOME/.config/iphone-onedrive-backup/backup.log"
```

### Other commands

| Command | What it does |
|---|---|
| `iphone-backup status` | How many files backed up / failed |
| `iphone-backup watch`  | Run the watcher in the foreground (Ctrl-C to stop) |
| `iphone-backup reset`  | Forget history (next backup re-uploads everything) |
| `iphone-backup doctor` | Diagnose tools / device / sign-in |
| `iphone-backup --version` | Show version |

To remove the auto-start agent:

```bash
launchctl bootout gui/$(id -u)/com.iphonebackup.watcher
rm ~/Library/LaunchAgents/com.iphonebackup.watcher.plist
```

---

## Configuration

Config lives at `~/.config/iphone-onedrive-backup/config.json`
(see `config.example.json`). Notable options:

| Key | Default | Meaning |
|---|---|---|
| `backend` | `rclone` | `rclone` or `graph` |
| `rclone_remote` | `onedrive` | Name of your configured rclone remote |
| `remote_base_folder` | `iPhone Backup` | Top OneDrive folder |
| `organize_by` | `date` | `date` (YYYY/MM), `dcim` (mirror phone folders), or `flat` |
| `poll_interval_seconds` | `5` | How often the watcher checks for a connected phone |
| `include_extensions` | photo+video list | File types to back up |

All local state (manifest, logs) stays in that same folder. Nothing secret is
ever committed to git (see `.gitignore`). Your OneDrive token is stored by rclone
in its own config (`~/.config/rclone/rclone.conf`).

---

## Notes & limitations

- The first backup of a large library uploads one file per `rclone` call, so it
  can take a while; subsequent connects only handle the handful of new photos.
- **Capture date** for the `date` layout comes from the file's modification time
  on the phone, which matches when the photo was taken in virtually all cases.
- **Deletions are not mirrored.** Removing a photo from your phone does not
  remove it from OneDrive — this is a backup, not a two-way sync.
- **Live Photos** upload as their still (HEIC) + the paired video (MOV).
- For full originals (not iCloud placeholders), set *Settings → Photos →
  Download and Keep Originals* on the iPhone.

---

## Advanced: use the built-in Graph backend instead

If you have an Azure/M365 directory and prefer not to use rclone, the tool has a
native Microsoft Graph uploader:

1. Register a public-client app in <https://entra.microsoft.com> (App
   registrations → New registration → *Personal Microsoft accounts only*),
   enable **Allow public client flows**, and copy the **Application (client) ID**.
2. `pip install -r requirements.txt` (installs `msal` + `requests`).
3. `iphone-backup init` → choose backend `graph`, paste the client ID.
4. `iphone-backup login` → device-code sign-in.

Everything else (device handling, dedup, auto-start) is identical.

---

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest         # 28 tests, no Mac/phone/network needed
```

| Module | Responsibility |
|---|---|
| `device.py` | libimobiledevice/ifuse: detect, pair, mount |
| `rclone_backend.py` | OneDrive upload via the rclone CLI (default) |
| `graph.py` | OneDrive upload via Microsoft Graph (optional backend) |
| `manifest.py` | SQLite dedup / incremental tracking |
| `backup.py` | Orchestration: mount → scan → upload new |
| `watcher.py` | Poll for connect → trigger backup |
| `installer.py` | launchd agent install |
| `remote_paths.py` | Pure path/chunk helpers (fully unit-tested) |
| `cli.py` | Command-line interface |
