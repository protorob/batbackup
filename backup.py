#!/usr/bin/env python3
"""
backup.py  v1.0
Zip source folders, upload to FTP / Nextcloud / Google Drive,
write a dated log, and email a summary report.

Usage:
    python backup.py                  # use ENABLE_* flags from CONFIGURATION
    python backup.py --ftp            # FTP only
    python backup.py --nc --gdrive    # Nextcloud + Google Drive
    python backup.py --ftp --nc --gdrive  # all three (same as default)

Requirements:
    Python 3.8+
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib webdavclient3
"""

import os
import sys
import shutil
import zipfile
import smtplib
import ftplib
import argparse
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    _GDRIVE_OK = True
except ImportError:
    _GDRIVE_OK = False

try:
    from webdav3.client import Client as WebDAVClient
    _WEBDAV_OK = True
except ImportError:
    _WEBDAV_OK = False


# ============================================================
#  CONFIGURATION  (edit only this section)
# ============================================================

_SCRIPT_DIR = Path(__file__).parent

# --- Destination toggles (used when no CLI flags are given)
ENABLE_FTP = True
ENABLE_NC  = True
ENABLE_GD  = True

# --- FTP
FTP_HOST = "ftp.example.com"
FTP_PORT = 21
FTP_USER = "ftpuser"
FTP_PASS = "ftppassword"
FTP_DEST = "backups"          # remote directory; created if absent
FTP_TLS  = True               # True = FTPS (recommended), False = plain FTP

# --- Nextcloud / WebDAV
NC_URL  = "https://yourhost/remote.php/dav/files/USERNAME"
NC_USER = "ncuser"
NC_PASS = "ncpassword"
NC_DEST = "Backups"           # remote path; nested paths like "A/B" are supported

# --- Google Drive
# Place credentials.json (from Google Cloud Console) next to this script.
# A token.json will be created automatically after the first browser auth.
GD_CREDENTIALS = str(_SCRIPT_DIR / "credentials.json")
GD_TOKEN       = str(_SCRIPT_DIR / "token.json")
GD_DEST        = "Backups"   # Drive folder; nested paths like "A/B" are supported

# --- Archive
ZIP_PREFIX = "backup"         # archive name: backup_FolderName_2026-01-01.zip

# --- Logging
LOG_DIR = r"C:\Logs\batbackup"

# --- Email (SMTP)
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587
SMTP_USER  = "you@gmail.com"
SMTP_PASS  = "abcd efgh ijkl mnop"   # Gmail: use an App Password
EMAIL_FROM = "you@gmail.com"
EMAIL_TO   = "recipient@example.com"

# --- Source folders
FOLDERS = [
    r"C:\Users\YourName\Documents",
    r"D:\Projects\important",
    # r"E:\another\path",
]

# ============================================================
#  END OF CONFIGURATION
# ============================================================

_GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
log = logging.getLogger("backup")


# ---- Logging -------------------------------------------------------

def setup_logging() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"backup_{today}.log"
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.addHandler(fh)
    log.addHandler(ch)
    return log_file


# ---- CLI args ------------------------------------------------------

def parse_args() -> dict:
    parser = argparse.ArgumentParser(
        description="Backup folders to FTP, Nextcloud, and/or Google Drive."
    )
    parser.add_argument("--ftp",    action="store_true", help="Upload to FTP")
    parser.add_argument("--nc",     action="store_true", help="Upload to Nextcloud/WebDAV")
    parser.add_argument("--gdrive", action="store_true", help="Upload to Google Drive")
    args = parser.parse_args()
    # If any flag is given, use only those; otherwise fall back to ENABLE_* config
    any_given = args.ftp or args.nc or args.gdrive
    return {
        "ftp":    args.ftp    if any_given else ENABLE_FTP,
        "nc":     args.nc     if any_given else ENABLE_NC,
        "gdrive": args.gdrive if any_given else ENABLE_GD,
    }


# ---- ZIP -----------------------------------------------------------

def zip_folder(src: Path, dst: Path) -> bool:
    try:
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in src.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(src.parent))
        return True
    except Exception as exc:
        log.error(f"  Zip failed: {exc}")
        return False


# ---- FTP -----------------------------------------------------------

def upload_ftp(zip_path: Path) -> bool:
    try:
        cls = ftplib.FTP_TLS if FTP_TLS else ftplib.FTP
        with cls() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
            ftp.login(FTP_USER, FTP_PASS)
            if FTP_TLS:
                ftp.prot_p()
            try:
                ftp.cwd(FTP_DEST)
            except ftplib.error_perm:
                ftp.mkd(FTP_DEST)
                ftp.cwd(FTP_DEST)
            with open(zip_path, "rb") as f:
                ftp.storbinary(f"STOR {zip_path.name}", f)
        return True
    except Exception as exc:
        log.error(f"  FTP upload failed: {exc}")
        return False


# ---- Nextcloud / WebDAV --------------------------------------------

def _nc_ensure_path(client, path: str):
    """Create each directory level of path if it does not already exist."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        if not client.check(current):
            client.mkdir(current)


def upload_nc(zip_path: Path) -> bool:
    if not _WEBDAV_OK:
        log.error("  webdavclient3 not installed — run: pip install webdavclient3")
        return False
    try:
        client = WebDAVClient({
            "webdav_hostname": NC_URL,
            "webdav_login":    NC_USER,
            "webdav_password": NC_PASS,
        })
        _nc_ensure_path(client, NC_DEST)
        remote = f"{NC_DEST.rstrip('/')}/{zip_path.name}"
        client.upload_sync(remote_path=remote, local_path=str(zip_path))
        return True
    except Exception as exc:
        log.error(f"  Nextcloud upload failed: {exc}")
        return False


# ---- Google Drive --------------------------------------------------

def _get_drive_service():
    if not _GDRIVE_OK:
        raise RuntimeError(
            "Google libraries not installed — run: "
            "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
    creds = None
    if os.path.exists(GD_TOKEN):
        creds = Credentials.from_authorized_user_file(GD_TOKEN, _GDRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GD_CREDENTIALS, _GDRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GD_TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _gd_ensure_path(service, path: str) -> str:
    """Navigate or create each directory level of path; return the leaf folder ID."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    parent_id = "root"
    for part in parts:
        q = (
            f"name='{part}' and '{parent_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        res = service.files().list(q=q, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            parent_id = files[0]["id"]
        else:
            meta = {
                "name": part,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = service.files().create(body=meta, fields="id").execute()
            parent_id = folder["id"]
    return parent_id


def upload_gdrive(zip_path: Path) -> bool:
    try:
        service = _get_drive_service()
        folder_id = _gd_ensure_path(service, GD_DEST)
        meta = {"name": zip_path.name, "parents": [folder_id]}
        media = MediaFileUpload(str(zip_path), resumable=True)
        service.files().create(body=meta, media_body=media, fields="id").execute()
        return True
    except Exception as exc:
        log.error(f"  Google Drive upload failed: {exc}")
        return False


# ---- Email ---------------------------------------------------------

def send_email(err_count: int, log_file: Path, today: str):
    subject = (
        f"BACKUP ERRORS ({err_count}) - {today}"
        if err_count > 0
        else f"Backup OK - {today}"
    )
    log.info(f"Sending email: {subject}")
    body = log_file.read_text(encoding="utf-8") if log_file.exists() else "(log not found)"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        log.info("Email sent OK")
    except Exception as exc:
        log.error(f"Email failed: {exc}")


# ---- Main ----------------------------------------------------------

def main():
    dest = parse_args()
    log_file = setup_logging()
    today = datetime.now().strftime("%Y-%m-%d")
    start = datetime.now().strftime("%H:%M:%S")

    active = ", ".join(k.upper() for k, v in dest.items() if v) or "NONE"
    log.info("=" * 48)
    log.info(f"  BACKUP started: {today} {start}")
    log.info(f"  Destinations  : {active}")
    log.info("=" * 48)

    if not any(dest.values()):
        log.error("No destinations enabled. Use --ftp, --nc, --gdrive or set ENABLE_* in config.")
        sys.exit(1)

    tmp_dir = Path(tempfile.mkdtemp(prefix="backup_"))
    err_count = 0

    upload_steps = [
        ("ftp",    "FTP",          upload_ftp),
        ("nc",     "Nextcloud",    upload_nc),
        ("gdrive", "Google Drive", upload_gdrive),
    ]

    try:
        for i, folder in enumerate(FOLDERS, 1):
            src = Path(folder)
            log.info("")
            log.info(f"[FOLDER {i}/{len(FOLDERS)}] {src}")

            if not src.is_dir():
                log.error(f"  [ERROR] Folder not found: {src}")
                err_count += 1
                continue

            zip_name = f"{ZIP_PREFIX}_{src.name}_{today}.zip"
            zip_path = tmp_dir / zip_name
            log.info(f"  Archive : {zip_name}")
            log.info("  Zipping ...")

            if not zip_folder(src, zip_path):
                err_count += 1
                continue
            log.info("  Zip     : OK")

            for key, label, fn in upload_steps:
                if dest[key]:
                    log.info(f"  Upload  : {label} ...")
                    if fn(zip_path):
                        log.info(f"  Upload  : {label} OK")
                    else:
                        err_count += 1

            zip_path.unlink(missing_ok=True)
            log.info("  Temp zip removed")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    end = datetime.now().strftime("%H:%M:%S")
    log.info("")
    log.info("=" * 48)
    log.info(f"  FINISHED: {today} {end}")
    log.info(f"  Result  : {'ALL OK' if err_count == 0 else f'{err_count} ERROR(S) -- check log'}")
    log.info("=" * 48)

    send_email(err_count, log_file, today)
    sys.exit(1 if err_count > 0 else 0)


if __name__ == "__main__":
    main()
