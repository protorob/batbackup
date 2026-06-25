# backup.py — Python edition

A Python script that zips one or more folders and uploads them to FTP, Nextcloud, and/or Google Drive. After each run it saves a dated log file and sends an email report with the outcome.

This is the Python replacement for `batbackup.bat`. It requires no rclone and no PowerShell, which eliminates the security and antivirus friction that the batch version causes on Windows 11.

## Why Python instead of batch

The batch script spawns `powershell -ExecutionPolicy Bypass` for zipping and emailing. This pattern matches common malware signatures, so Windows Defender and third-party antivirus products often block or quarantine it. Python handles zipping (`zipfile`), email (`smtplib`), and all uploads natively through its standard library and trusted third-party packages — no execution policy bypass needed.

## Features

- Zips each source folder into a dated archive (`PREFIX_FolderName_2026-06-18.zip`)
- Uploads to FTP, Nextcloud/WebDAV, and Google Drive — all natively, no rclone
- Toggle any destination on/off with CLI flags or config variables
- Writes a timestamped log file per day to a configurable path
- Emails a summary on completion — subject reflects success or error count
- Returns exit code `0` (success) or `1` (one or more errors), compatible with Task Scheduler

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.8+ | Available free from [python.org](https://www.python.org/downloads/) or the Microsoft Store |
| `google-api-python-client` | Official Google Drive client |
| `google-auth-httplib2` | Google auth transport |
| `google-auth-oauthlib` | Google OAuth2 flow |
| `webdavclient3` | WebDAV client for Nextcloud |
| SMTP access | Gmail, Outlook, or any SMTP server with STARTTLS on port 587 |

Install all third-party packages at once:

```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib webdavclient3
```

FTP and email use Python's built-in `ftplib` and `smtplib` — no extra install needed.

## Quick start

### 1. Install Python and packages

Download Python 3 from [python.org](https://www.python.org/downloads/) or install it from the Microsoft Store. During installation, tick **Add Python to PATH**.

Then open a Command Prompt and run:

```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib webdavclient3
```

### 2. Set up Google Drive access (one time)

The script uses the official Google Drive API with OAuth2. You need to create a project in Google Cloud Console and download a credentials file.

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Library**, search for **Google Drive API**, and click **Enable**
4. Go to **APIs & Services → OAuth consent screen**
   - Choose **External** (or Internal if using Google Workspace)
   - Fill in the app name (e.g. `My Backup Script`) and your email
   - Under **Scopes**, add `.../auth/drive.file` (allows the script to manage only files it creates)
   - Add your Google account email as a **Test user**
5. Go to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON file and rename it to `credentials.json`
6. Place `credentials.json` in the same folder as `backup.py`

**First run:** the script will open a browser window asking you to authorize access to your Google Drive. After you approve, it saves a `token.json` next to the script. All future runs use that token silently — the browser will not open again unless the token is deleted.

> **Scheduled tasks:** run the script manually at least once interactively so the browser auth completes and `token.json` is created. After that the task runs unattended.

### 3. Configure the script

Open `backup.py` in any text editor and fill in the **CONFIGURATION** section at the top. Everything below the configuration block is handled automatically.

```python
# --- Destination toggles (used when no CLI flags are given)
ENABLE_FTP = True
ENABLE_NC  = True
ENABLE_GD  = True

# --- FTP
FTP_HOST = "ftp.example.com"
FTP_PORT = 21
FTP_USER = "ftpuser"
FTP_PASS = "ftppassword"
FTP_DEST = "backups"
FTP_TLS  = True   # True = FTPS, False = plain FTP

# --- Nextcloud / WebDAV
NC_URL  = "https://yourhost/remote.php/dav/files/USERNAME"
NC_USER = "ncuser"
NC_PASS = "ncpassword"
NC_DEST = "Backups"

# --- Google Drive
GD_CREDENTIALS = "credentials.json"   # place next to backup.py
GD_TOKEN       = "token.json"         # created automatically on first run
GD_DEST        = "Backups"

# --- Email
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587
SMTP_USER  = "you@gmail.com"
SMTP_PASS  = "abcd efgh ijkl mnop"   # Gmail: App Password
EMAIL_FROM = "you@gmail.com"
EMAIL_TO   = "recipient@example.com"

# --- Source folders
FOLDERS = [
    r"C:\Users\YourName\Documents",
    r"D:\Projects\important",
]
```

To add more folders, append lines to the `FOLDERS` list:

```python
FOLDERS = [
    r"C:\Users\YourName\Documents",
    r"D:\Projects\important",
    r"E:\another\folder",
]
```

### 4. Selecting destinations

**Via config (default):** set `ENABLE_FTP`, `ENABLE_NC`, and `ENABLE_GD` to `True` or `False` directly in the CONFIGURATION section. When you run the script with no arguments, these values are used.

**Via CLI flags (overrides config):** pass one or more of `--ftp`, `--nc`, `--gdrive`. When any flag is given, only the flagged destinations run — the config toggles are ignored for that run.

```
python backup.py                  # uses ENABLE_* from config
python backup.py --gdrive         # Google Drive only
python backup.py --ftp --nc       # FTP and Nextcloud only
python backup.py --ftp --nc --gdrive  # all three
```

This makes it easy to test one destination at a time or to run different destinations on different schedules from Task Scheduler.

### 5. Test a manual run

Open a Command Prompt, navigate to the folder containing `backup.py`, and run:

```
python backup.py
```

Watch the console output. When Google Drive runs for the first time, a browser window opens for authorization — approve it once and it will not appear again. Check the log file in `LOG_DIR` and confirm the zip files appeared in each remote destination.

### 6. Schedule with Windows Task Scheduler

1. Open **Task Scheduler** (`taskschd.msc`)
2. Click **Create Basic Task**
3. Set your trigger (daily, weekly, etc.)
4. Action: **Start a program**
   - Program: `python`
   - Arguments: `"C:\path\to\backup.py"` (or add `--gdrive` etc. to target a specific destination)
   - Start in: `C:\path\to\` (the folder containing `backup.py` and `credentials.json`)
5. Under **General**, check **Run whether user is logged on or not** and tick **Run with highest privileges** if the source folders require elevated access
6. Under **Settings**, tick **If the task fails, restart every** and set a retry interval if desired

> The script exits with code `0` on full success and `1` if any error occurred. Task Scheduler can be configured to alert or retry on non-zero exit codes.

## Log format

A new log file is created each day at `LOG_DIR\backup_YYYY-MM-DD.log`. Example output:

```
[10:00:01] ================================================
[10:00:01]   BACKUP started: 2026-06-18 10:00:01
[10:00:01]   Destinations  : FTP, NC, GDRIVE
[10:00:01] ================================================
[10:00:01]
[10:00:01] [FOLDER 1/2] C:\Users\YourName\Documents
[10:00:01]   Archive : backup_Documents_2026-06-18.zip
[10:00:01]   Zipping ...
[10:00:04]   Zip     : OK
[10:00:04]   Upload  : FTP ...
[10:00:07]   Upload  : FTP OK
[10:00:07]   Upload  : Nextcloud ...
[10:00:09]   Upload  : Nextcloud OK
[10:00:09]   Upload  : Google Drive ...
[10:00:11]   Upload  : Google Drive OK
[10:00:11]   Temp zip removed
...
[10:00:45] ================================================
[10:00:45]   FINISHED: 2026-06-18 10:00:45
[10:00:45]   Result  : ALL OK
[10:00:45] ================================================
[10:00:45]
[10:00:45] Sending email: Backup OK - 2026-06-18
[10:00:46] Email sent OK
```

On errors, lines are prefixed with `[ERROR]`. The email subject changes to `BACKUP ERRORS (N) - YYYY-MM-DD`.

## Email setup by provider

### Gmail

1. Enable 2-Step Verification on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Generate an App Password for "Mail"
4. Use that 16-character password (spaces included) as `SMTP_PASS`

```python
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
```

### Outlook / Microsoft 365

```python
SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587
```

### Dreamhost or custom SMTP

```python
SMTP_HOST = "smtp.dreamhost.com"
SMTP_PORT = 587
```

The script uses STARTTLS (port 587) for all providers. If your server only offers implicit SSL on port 465, switch to `smtplib.SMTP_SSL` in the `send_email` function.

## Nextcloud setup

The WebDAV URL for Nextcloud follows this pattern:

```
https://yourhost/remote.php/dav/files/YOUR_USERNAME
```

You can use your main Nextcloud password, but it is better to generate a dedicated app password: **Settings → Security → Devices & sessions → Create new app password**.

`NC_DEST` supports nested paths such as `"Projects/Backups"` — the script creates any missing directories automatically.

## Troubleshooting

**`ModuleNotFoundError: No module named 'google'`**
The Google libraries are not installed. Run:
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

**`ModuleNotFoundError: No module named 'webdav3'`**
The WebDAV library is not installed. Run:
```
pip install webdavclient3
```

**Google Drive: browser opens every time**
`token.json` is missing or was deleted. Let the browser flow complete once and the file will be recreated.

**Google Drive: token expires after a long period**
Delete `token.json` and run the script interactively once to re-authorize.

**Google Drive: `credentials.json` not found**
Make sure `credentials.json` is in the same folder as `backup.py`, or update `GD_CREDENTIALS` in the config to the full path of the file.

**Nextcloud upload fails with 401 Unauthorized**
Check `NC_USER`, `NC_PASS`, and `NC_URL`. Make sure the URL ends with your Nextcloud username, not just the host. If you recently changed your Nextcloud password, update `NC_PASS` or generate a new app password.

**FTP upload fails**
Test your FTP credentials with any FTP client (e.g. FileZilla) first. If the server uses implicit SSL (port 990), set `FTP_TLS = False` and configure the port accordingly — `ftplib.FTP_TLS` targets explicit FTPS (STARTTLS on port 21).

**Email not sending**
- Gmail: make sure you are using an App Password, not your account password
- Check that outbound port 587 is not blocked by your firewall or antivirus
- Test SMTP credentials with a standalone mail client before running the script

**Zip is empty or fails**
If a source folder contains files locked by another process (e.g. an open database), `zipfile` will raise an error on that file. The error message in the log will name the specific file. You can exclude locked files by catching `PermissionError` inside the zip loop if needed.

**Task Scheduler: script runs but nothing uploads**
The scheduled task likely runs as a different user who does not have `token.json` (for Drive) or whose environment Python is not in PATH. Fix:
- Use the full path to `python.exe` in the Task Scheduler action (e.g. `C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe`)
- Set **Start in** to the folder containing `backup.py` and `credentials.json`
- Run the script once interactively as the same user the task runs as, so `token.json` is created under that user's profile

## File structure

```
batbackup/
├── backup.py           # the script — edit CONFIGURATION section only
├── credentials.json    # downloaded from Google Cloud Console (you provide this)
├── token.json          # created automatically on first Google Drive auth
└── README_python.md    # this file
```

Logs are written to the path configured in `LOG_DIR` (default: `C:\Logs\batbackup\`), outside the repository.

## License

MIT
