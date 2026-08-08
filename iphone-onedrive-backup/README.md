# iPhone → OneDrive Photo Backup (macOS)

Automatically copy the photos and videos off your iPhone and upload the new
ones to **Microsoft OneDrive**. Plug your phone into your Mac and the backup
starts on its own — every time, only for photos it hasn't already saved.

- 📷 Reads full-resolution **originals** (HEIC, JPEG, PNG, MOV, MP4, DNG …) over USB
- ☁️ Uploads to OneDrive via the official Microsoft Graph API (resumable, chunked)
- 🔁 **Incremental** — a local database remembers what's uploaded, so each run only sends new photos
- ⚡ **Auto-start on connect** — a background agent watches for your phone and fires the backup
- 🗂️ Organizes uploads by capture date (`iPhone Backup/2024/03/IMG_0001.HEIC`)

---

## How it works

macOS doesn't let software read an iPhone's filesystem directly. This tool uses
[`libimobiledevice`](https://libimobiledevice.org/) + `ifuse` — the same open
protocol Finder/iTunes uses — to mount the phone's camera roll (`DCIM`) as a
folder, then walks it and uploads anything new.

```
iPhone (USB) → ifuse mount (/DCIM) → scan → skip already-uploaded → upload new → OneDrive
                                                     ▲
                                          local manifest.db (SQLite)
```

A launchd background agent runs `iphone-backup watch`, which polls for a
connected device and runs a backup the moment one appears.

---

## Requirements

- macOS (Intel or Apple Silicon)
- Python 3.10+
- A Microsoft account with OneDrive (personal outlook/hotmail/live, or work/school)
- Homebrew

---

## Setup

### 1. Install the phone-access tools

```bash
brew install libimobiledevice ifuse
```

`ifuse` needs **macFUSE**. If `brew install ifuse` doesn't pull it in:

```bash
brew install --cask macfuse
```

Then open **System Settings → Privacy & Security** and click **Allow** for the
macFUSE system extension (you may need to reboot once). This is a one-time step.

### 2. Install this tool

```bash
cd iphone-onedrive-backup
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # installs deps and the `iphone-backup` command
```

(Or `pip install -r requirements.txt` and run it as `python -m iphone_backup`.)

### 3. Register a free Microsoft/Azure app (one time, ~2 minutes)

The tool signs in as *you* to upload to *your* OneDrive. Microsoft requires an
app registration to get a **client ID**. There is no cost and no client secret.

1. Go to <https://entra.microsoft.com> → **Applications → App registrations → New registration**.
   (Direct link: <https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade>.)
2. **Name:** anything, e.g. `iPhone OneDrive Backup`.
3. **Supported account types:** choose **Personal Microsoft accounts only**
   (or "…and personal Microsoft accounts" if you also use a work account).
4. Leave Redirect URI blank. Click **Register**.
5. On the app's **Overview** page, copy the **Application (client) ID**.
6. Go to **Authentication → Advanced settings** and set
   **"Allow public client flows"** to **Yes**. Save.

> Account type mapping used below:
> personal account → `consumers`, work/school → `organizations`, both → `common`.

### 4. Configure and sign in

```bash
iphone-backup init      # paste your client ID + pick account type + folder name
iphone-backup login     # opens a device-code sign-in; approve in your browser
```

`login` prints something like *"To sign in, use a web browser to open
https://microsoft.com/devicelogin and enter the code XXXX-XXXX."* Do that once;
the token is cached and refreshed automatically afterward.

### 5. Check everything

```bash
iphone-backup doctor
```

You want all ✓: tools installed, device connected + paired (unlock the phone and
tap **Trust This Computer** the first time), and OneDrive signed in.

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
| `client_id` | — | Your Azure app's client ID |
| `tenant` | `consumers` | `consumers` (personal), `organizations` (work), or `common` |
| `remote_base_folder` | `iPhone Backup` | Top OneDrive folder |
| `organize_by` | `date` | `date` (YYYY/MM), `dcim` (mirror phone folders), or `flat` |
| `chunk_size_mib` | `10` | Upload chunk size for large videos |
| `poll_interval_seconds` | `5` | How often the watcher checks for a connected phone |
| `include_extensions` | photo+video list | File types to back up |

All local state (token, manifest, logs) stays in that same folder. Nothing
secret is ever committed to git (see `.gitignore`).

---

## Notes & limitations

- **Capture date** for the `date` layout comes from the file's modification
  time on the phone, which matches when the photo was taken in virtually all
  cases. (EXIF-based dating is a natural future enhancement.)
- **Deletions are not mirrored.** Removing a photo from your phone does not
  remove it from OneDrive — this is a backup, not a two-way sync.
- **Live Photos** upload as their still (HEIC) + the paired video (MOV) as two
  files, exactly as they exist on the phone.
- Uploading via the phone's own **iCloud "Optimize Storage"** can leave low-res
  placeholders on the device; for full originals, set *Settings → Photos →
  Download and Keep Originals* on the iPhone.

---

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest         # 25 tests, no Mac/phone/network needed
```

The code is split so the risky, platform-specific parts are isolated:

| Module | Responsibility |
|---|---|
| `device.py` | libimobiledevice/ifuse: detect, pair, mount |
| `graph.py` | OneDrive auth (MSAL device code) + chunked upload |
| `manifest.py` | SQLite dedup / incremental tracking |
| `backup.py` | Orchestration: mount → scan → upload new |
| `watcher.py` | Poll for connect → trigger backup |
| `installer.py` | launchd agent install |
| `remote_paths.py` | Pure path/chunk helpers (fully unit-tested) |
| `cli.py` | Command-line interface |
```
