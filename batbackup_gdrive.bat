@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  BATBACKUP_GDRIVE.BAT  v1.0
::  Zip source folders, upload to Google Drive,
::  write a dated log, and email a summary report.
::
::  REQUIREMENTS
::    rclone  https://rclone.org/downloads/  (single .exe, no install)
::    Run once before using this script:
::      rclone config  ->  add:
::        type "drive"  for Google Drive
::    Windows 10+ (Compress-Archive is built-in via PowerShell)
::    Gmail: create an App Password at myaccount.google.com/apppasswords
::           use it as SMTP_PASS instead of your account password
:: ============================================================


:: ============================================================
::  SECTION 1 - CONFIGURATION  (only edit this section)
:: ============================================================

:: -- Path to rclone executable
set "RCLONE=C:\tools\rclone\rclone.exe"

:: -- Remote name exactly as typed in: rclone config
set "GD_REMOTE=my-gdrive"
set "GD_DEST=Backups"

:: -- Archive name prefix  ->  PREFIX_FolderName_2026-06-18.zip
set "ZIP_PREFIX=backup"

:: -- Directory where log files are saved (one file per day)
set "LOG_DIR=C:\Logs\batbackup"

:: -- SMTP settings
set "SMTP_HOST=smtp.gmail.com"
set "SMTP_PORT=587"
set "SMTP_USER=you@gmail.com"
set "SMTP_PASS=abcd efgh ijkl mnop"
set "EMAIL_FROM=you@gmail.com"
set "EMAIL_TO=recipient@example.com"

:: -- Source folders (add/remove lines; keep FOLDER_COUNT in sync)
set "FOLDER_1=C:\Users\YourName\Documents"
set "FOLDER_2=D:\Projects\important"
:: set "FOLDER_3=E:\another\path"
set "FOLDER_COUNT=2"


:: ============================================================
::  SECTION 2 - INIT
:: ============================================================

:: Use PowerShell for a locale-independent ISO date/time
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format HH:mm:ss"') do set "START_TIME=%%t"

set "LOG_FILE=%LOG_DIR%\backup_%TODAY%.log"
set "TMP_DIR=%TEMP%\batbackup_%TODAY%"
set "ERR_COUNT=0"

if not exist "%LOG_DIR%"  mkdir "%LOG_DIR%"  2>nul
if not exist "%TMP_DIR%"  mkdir "%TMP_DIR%"  2>nul

call :LOG "================================================"
call :LOG "  BATBACKUP started: %TODAY% %START_TIME%"
call :LOG "================================================"


:: ============================================================
::  SECTION 3 - MAIN LOOP
:: ============================================================

for /L %%i in (1,1,%FOLDER_COUNT%) do (
    call :PROCESS_FOLDER %%i
)


:: ============================================================
::  SECTION 4 - SUMMARY AND EMAIL
:: ============================================================

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format HH:mm:ss"') do set "END_TIME=%%t"

call :LOG ""
call :LOG "================================================"
call :LOG "  FINISHED: %TODAY% %END_TIME%"
if %ERR_COUNT% equ 0 (
    call :LOG "  Result  : ALL OK"
) else (
    call :LOG "  Result  : %ERR_COUNT% ERROR(S) -- check log"
)
call :LOG "================================================"

rd /s /q "%TMP_DIR%" 2>nul

call :SEND_EMAIL

if %ERR_COUNT% gtr 0 (exit /b 1) else (exit /b 0)


:: ============================================================
::  SUB: PROCESS_FOLDER  <folder-index>
:: ============================================================
:PROCESS_FOLDER
call set "SRC=%%FOLDER_%1%%"

if "!SRC!"=="" (
    call :LOG ""
    call :LOG "[WARN ] FOLDER_%1 is not defined -- skipping"
    goto :eof
)

if not exist "!SRC!\" (
    call :LOG ""
    call :LOG "[ERROR] Folder %1 not found: !SRC!"
    set /a ERR_COUNT+=1
    goto :eof
)

:: Extract base name from the full path
for %%B in ("!SRC!") do set "FNAME=%%~nxB"
set "ZIPNAME=%ZIP_PREFIX%_!FNAME!_%TODAY%.zip"
set "ZIPPATH=%TMP_DIR%\!ZIPNAME!"

call :LOG ""
call :LOG "[FOLDER %1/%FOLDER_COUNT%] !SRC!"
call :LOG "  Archive : !ZIPNAME!"
call :LOG "  Zipping ..."

:: Pass paths via env vars to avoid quote/space issues in PowerShell
set "PS_SRC=!SRC!"
set "PS_DST=!ZIPPATH!"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -LiteralPath $env:PS_SRC -DestinationPath $env:PS_DST -Force"
set "ZIP_ERR=!errorlevel!"

if !ZIP_ERR! neq 0 (
    call :LOG "  [ERROR] Zip failed (PowerShell exit !ZIP_ERR!)"
    set /a ERR_COUNT+=1
    goto :eof
)

call :LOG "  Zip     : OK"

call :UPLOAD "!ZIPPATH!" "%GD_REMOTE%:%GD_DEST%"    "Google Drive"

del "!ZIPPATH!" 2>nul
call :LOG "  Temp zip removed"
goto :eof


:: ============================================================
::  SUB: UPLOAD  <zip-path>  <remote:dest-path>  <label>
:: ============================================================
:UPLOAD
call :LOG "  Upload  : %~3 ..."
"%RCLONE%" copy "%~1" "%~2" --log-level ERROR
set "UP_ERR=!errorlevel!"
if !UP_ERR! equ 0 (
    call :LOG "  Upload  : %~3 OK"
) else (
    call :LOG "  [ERROR] %~3 upload failed (rclone exit !UP_ERR!)"
    set /a ERR_COUNT+=1
)
goto :eof


:: ============================================================
::  SUB: LOG  <message>
:: ============================================================
:LOG
echo [%TIME:~0,8%] %~1
echo [%TIME:~0,8%] %~1 >> "%LOG_FILE%"
goto :eof


:: ============================================================
::  SUB: SEND_EMAIL
:: ============================================================
:SEND_EMAIL
if %ERR_COUNT% gtr 0 (
    set "ESUBJ=BACKUP ERRORS (%ERR_COUNT%) - %TODAY%"
) else (
    set "ESUBJ=Backup OK - %TODAY%"
)
call :LOG ""
call :LOG "Sending email: !ESUBJ!"

:: All values go through environment variables so no quoting issues
:: arise from passwords or paths that contain special characters.
set "PS_SMTP_HOST=%SMTP_HOST%"
set "PS_SMTP_PORT=%SMTP_PORT%"
set "PS_SMTP_USER=%SMTP_USER%"
set "PS_SMTP_PASS=%SMTP_PASS%"
set "PS_FROM=%EMAIL_FROM%"
set "PS_TO=%EMAIL_TO%"
set "PS_SUBJ=!ESUBJ!"
set "PS_LOG=%LOG_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$body = (Get-Content $env:PS_LOG -Encoding UTF8) -join \"`r`n\";" ^
    "$creds = New-Object Management.Automation.PSCredential($env:PS_SMTP_USER, (ConvertTo-SecureString $env:PS_SMTP_PASS -AsPlainText -Force));" ^
    "$smtp = New-Object Net.Mail.SmtpClient($env:PS_SMTP_HOST, [int]$env:PS_SMTP_PORT);" ^
    "$smtp.EnableSsl = $true;" ^
    "$smtp.Credentials = $creds;" ^
    "$smtp.Send($env:PS_FROM, $env:PS_TO, $env:PS_SUBJ, $body);" ^
    "Write-Host 'Email sent to' $env:PS_TO"

set "MAIL_ERR=!errorlevel!"
if !MAIL_ERR! equ 0 (
    call :LOG "Email sent OK"
) else (
    call :LOG "[ERROR] Email failed to send (exit !MAIL_ERR!)"
)
goto :eof
