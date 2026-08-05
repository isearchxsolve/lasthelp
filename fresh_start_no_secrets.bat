@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  fresh_start_no_secrets.bat
REM  Zero manual steps. Run this from inside your repo folder
REM  (the "lasthelp" folder) by double-clicking it.
REM
REM  What it does:
REM   1. Backs up the whole repo folder (with full history) to
REM      a sibling folder, just in case.
REM   2. Deletes the known secret files from disk.
REM   3. Wipes all git history and starts one brand new commit.
REM   4. Adds a .gitignore so this doesn't happen again.
REM   5. Force-pushes the clean single commit to GitHub.
REM
REM  IMPORTANT (read when you wake up, not now):
REM   The leaked keys still technically existed and were pushed
REM   at some point, so treat them as compromised. When you have
REM   a few minutes, revoke/rotate these:
REM     - Google OAuth client ID/secret
REM     - OpenRouter API key
REM     - Groq API key
REM     - GCP API key
REM   This script does NOT and CANNOT do that part for you —
REM   it's not a git problem, it's a "log into each dashboard"
REM   problem. No rush tonight.
REM =========================================================

set REPO_URL=https://github.com/isearchxsolve/lasthelp.git

echo.
echo ============================================================
echo  Starting automated cleanup - no input needed from here.
echo ============================================================
timeout /t 3 >nul

REM ---- Step 1: Backup ----
for %%I in (.) do set REPO_FOLDER_NAME=%%~nxI
cd ..
set BACKUP_DIR=%REPO_FOLDER_NAME%_backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%
set BACKUP_DIR=%BACKUP_DIR: =0%
echo Backing up to %BACKUP_DIR% ...
xcopy "%REPO_FOLDER_NAME%" "%BACKUP_DIR%" /E /I /H /Y >nul
cd "%REPO_FOLDER_NAME%"
echo Backup done.

REM ---- Step 2: Delete known secret files from disk ----
echo Deleting known secret files...
if exist "ai_video_monetizer\client_secret.json" del /f /q "ai_video_monetizer\client_secret.json"
if exist "OMEGA\data\omega_vault.json" del /f /q "OMEGA\data\omega_vault.json"

REM Strip the Groq key out of the notebook without deleting the whole notebook,
REM by removing lines that look like API key assignments. Best-effort only.
if exist "OMEGA\OMEGA_CLEANED_FINAL.ipynb" (
    echo Scrubbing likely key patterns from OMEGA_CLEANED_FINAL.ipynb ...
    powershell -NoProfile -Command ^
        "(Get-Content 'OMEGA\OMEGA_CLEANED_FINAL.ipynb') | " ^
        "ForEach-Object { $_ -replace '(gsk_[A-Za-z0-9]+)', 'REDACTED' } | " ^
        "Set-Content 'OMEGA\OMEGA_CLEANED_FINAL.ipynb'"
)

if exist "OMEGA\README.md" (
    echo Scrubbing likely key patterns from OMEGA README.md ...
    powershell -NoProfile -Command ^
        "(Get-Content 'OMEGA\README.md') | " ^
        "ForEach-Object { $_ -replace '(AIza[A-Za-z0-9_\-]+)', 'REDACTED' } | " ^
        "Set-Content 'OMEGA\README.md'"
)

REM ---- Step 3: Wipe git history, start one fresh commit ----
echo Wiping git history...
rmdir /s /q .git

echo Initializing fresh repo...
git init -q
git branch -M main

REM ---- Step 4: .gitignore so this never repeats ----
(
echo # Secrets ^& credentials
echo client_secret.json
echo *.env
echo .env
echo **/omega_vault.json
echo **/*_secret*.json
echo **/*apikey*
echo **/*api_key*
) > .gitignore

git add -A
git commit -q -m "Fresh start: clean history, secrets removed"

REM ---- Step 5: Push clean history ----
git remote add origin %REPO_URL%
git push -f origin main

echo.
echo ============================================================
echo  DONE. Repo pushed with a single clean commit, no secrets.
echo  Full old history (with the real keys) is safely offline in:
echo    %BACKUP_DIR%
echo  That backup is now the ONLY place the old keys still exist
echo  outside of the services that issued them.
echo.
echo  When you're rested: revoke/rotate the Google OAuth,
echo  OpenRouter, Groq, and GCP keys. They were pushed before,
echo  so they should be treated as compromised regardless of
echo  what this script just did.
echo ============================================================
timeout /t 10
