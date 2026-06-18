# batbackup

A Windows batch script that zips one or more folders and uploads them to FTP, Nextcloud, and Google Drive. After each run it saves a dated log file and sends an email report with the outcome.

## Features

- Zips each source folder into a dated archive (`PREFIX_FolderName_2026-06-18.zip`)
- Uploads to all three destinations in one run via [rclone](https://rclone.org)
- Writes a timestamped log file per day to a configurable path
- Emails a summary on completion — subject line reflects success or error count
- Returns exit code `0` (success) or `1` (one or more errors), compatible with Task Scheduler alerting
- No dependencies beyond rclone and the built-in Windows PowerShell

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10 or later | `Compress-Archive` is built into PowerShell 5+ |
| [rclone](https://rclone.org/downloads/) | Single `.exe`, no installer needed |
| SMTP access | Gmail, Outlook, or any SMTP server |

## Quick start

### 1. Download rclone

Download the `rclone.exe` binary from [rclone.org/downloads](https://rclone.org/downloads/) and place it anywhere on your machine (e.g. `C:\tools\rclone\rclone.exe`).

### 2. Configure rclone remotes

Run `rclone config` once for each destination. You need three remotes total.

#### FTP

```
rclone config
> n  (new remote)
  name: my-ftp
  type: ftp
  host: ftp.yourserver.com
  user: ftpuser
  pass: (enter password, rclone will obfuscate it)
```

#### Nextcloud (WebDAV)

```
rclone config
> n
  name: my-nextcloud
  type: webdav
  url:  https://yournextcloud.com/remote.php/dav/files/USERNAME
  vendor: nextcloud
  user: your-nc-username
  pass: (your Nextcloud password or app token)
```

> **Tip:** In Nextcloud, go to **Settings → Security → Devices & sessions** to generate a dedicated app password instead of using your main password.

#### Google Drive

```
rclone config
> n
  name: my-gdrive
  type: drive
  (follow the OAuth flow — rclone opens a browser for authorization)
```

> When running as a scheduled task (no desktop/browser), configure the remote interactively first on the same machine, then use it unattended. The OAuth token is stored in `%APPDATA%\rclone\rclone.conf`.

#### Verify your remotes

```bat
rclone lsd my-ftp:
rclone lsd my-nextcloud:Backups
rclone lsd my-gdrive:Backups
```

### 3. Edit the CONFIG section in `batbackup.bat`

Open `batbackup.bat` in any text editor and fill in **Section 1** only. Everything else is managed by the script.

```bat
:: Path to rclone executable
set "RCLONE=C:\tools\rclone\rclone.exe"

:: Remote names — must match what you typed in rclone config
set "FTP_REMOTE=my-ftp"
set "FTP_DEST=backups"

set "NC_REMOTE=my-nextcloud"
set "NC_DEST=Backups"

set "GD_REMOTE=my-gdrive"
set "GD_DEST=Backups"

:: Archive name prefix  ->  PREFIX_FolderName_2026-06-18.zip
set "ZIP_PREFIX=backup"

:: Log directory (one file per day)
set "LOG_DIR=C:\Logs\batbackup"

:: SMTP settings
set "SMTP_HOST=smtp.gmail.com"
set "SMTP_PORT=587"
set "SMTP_USER=you@gmail.com"
set "SMTP_PASS=abcd efgh ijkl mnop"
set "EMAIL_FROM=you@gmail.com"
set "EMAIL_TO=recipient@example.com"

:: Source folders — add/remove lines and update FOLDER_COUNT
set "FOLDER_1=C:\Users\YourName\Documents"
set "FOLDER_2=D:\Projects\important"
set "FOLDER_COUNT=2"
```

To add more folders, append lines and increment the counter:

```bat
set "FOLDER_3=E:\another\folder"
set "FOLDER_COUNT=3"
```

### 4. Test a manual run

Open a Command Prompt and run:

```bat
C:\path\to\batbackup.bat
```

Check the console output and the log file in `LOG_DIR`. Confirm that the zip files appeared in each remote destination.

### 5. Schedule with Windows Task Scheduler

1. Open **Task Scheduler** (`taskschd.msc`)
2. Click **Create Basic Task**
3. Set your trigger (daily, weekly, etc.)
4. Action: **Start a program**
   - Program: `cmd.exe`
   - Arguments: `/c "C:\path\to\batbackup.bat"`
5. Under **General**, check **Run whether user is logged on or not** and tick **Run with highest privileges** if the folders require elevated access
6. Under **Settings**, tick **If the task fails, restart every** and set a retry interval if desired

> The task exits with code `0` on full success and `1` if any error occurred. Task Scheduler can be configured to alert or retry on non-zero exit codes.

## Log format

A new log file is created each day at `LOG_DIR\backup_YYYY-MM-DD.log`. Example output:

```
[10:00:01] ================================================
[10:00:01]   BATBACKUP started: 2026-06-18 10:00:01
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
3. Generate an App Password for "Mail" / "Windows Computer"
4. Use that 16-character password (with spaces) as `SMTP_PASS`

```bat
set "SMTP_HOST=smtp.gmail.com"
set "SMTP_PORT=587"
```

### Outlook / Microsoft 365

```bat
set "SMTP_HOST=smtp.office365.com"
set "SMTP_PORT=587"
```

### Custom SMTP server

```bat
set "SMTP_HOST=mail.yourserver.com"
set "SMTP_PORT=587"
```

If your server uses port 465 (implicit SSL) instead of 587 (STARTTLS), the PowerShell `Net.Mail.SmtpClient` used here does not support implicit SSL. In that case, ask your provider for a STARTTLS endpoint or switch to port 587.

## Troubleshooting

**Zip fails with exit code 1**
PowerShell's `Compress-Archive` returns an error if the source folder is empty or if it cannot access a file (e.g. locked by another process). Check the console output for the PowerShell error message.

**rclone upload fails**
Run the upload command manually to see the full error:
```bat
rclone copy C:\path\to\file.zip my-ftp:backups -v
```
Common causes: wrong remote name, wrong destination path, credential expired (re-run `rclone config` to update), or network issue.

**Google Drive OAuth token expires**
Rclone stores the token in `%APPDATA%\rclone\rclone.conf`. If uploads start failing after a long period, re-authorize by running `rclone config` and reconnecting the `drive` remote.

**Email not sending**
- Confirm SMTP credentials are correct by testing with a mail client first
- Gmail users: make sure you are using the App Password, not the account password
- Check if your antivirus or firewall is blocking outbound port 587

**Folder paths with `!` characters**
The script uses CMD delayed expansion (`!var!`), which treats `!` as a delimiter. Avoid using `!` in folder names or paths listed in `FOLDER_N`. This does not affect file names inside the folders, only the paths in the config section.

**Task Scheduler: script runs but nothing uploads**
This is usually a missing rclone config context. The scheduled task runs as a different user (SYSTEM or a service account) that does not have the rclone remotes configured. Fix: either run `rclone config` as that user, or point `RCLONE_CONFIG` to the config file of your interactive user:
```bat
:: Add this line near the top of Section 1
set "RCLONE_CONFIG=C:\Users\YourName\AppData\Roaming\rclone\rclone.conf"
```

## File structure

```
batbackup/
├── batbackup.bat   # the script — edit Section 1 only
└── README.md       # this file
```

Logs are written to the path configured in `LOG_DIR` (default: `C:\Logs\batbackup\`), outside the repository.

## License

MIT
