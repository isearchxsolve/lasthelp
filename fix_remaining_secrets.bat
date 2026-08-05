@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  fix_remaining_secrets.bat
REM  Run this from inside your "lasthelp" folder.
REM  Removes the newly-flagged secret files/lines, wipes
REM  history again, and force-pushes clean.
REM  No typing needed.
REM =========================================================

echo.
echo ============================================================
echo  Deleting known secret-containing files...
echo ============================================================
if exist "OMEGA\key.txt" del /f /q "OMEGA\key.txt"
if exist "ases_v3_1\.env.example" del /f /q "ases_v3_1\.env.example"

echo.
echo ============================================================
echo  Scrubbing README.md of any remaining key-like strings...
echo ============================================================
if exist "OMEGA\README.md" (
    powershell -NoProfile -Command ^
        "(Get-Content 'OMEGA\README.md') | " ^
        "ForEach-Object { $_ -replace '(gh[pousr]_[A-Za-z0-9]{20,})', 'REDACTED' } | " ^
        "ForEach-Object { $_ -replace '(sk-or-[A-Za-z0-9\-]+)', 'REDACTED' } | " ^
        "ForEach-Object { $_ -replace '(gsk_[A-Za-z0-9]+)', 'REDACTED' } | " ^
        "Set-Content 'OMEGA\README.md'"
)

echo.
echo ============================================================
echo  Wiping git history again and starting one fresh commit...
echo ============================================================
rmdir /s /q .git
git init -q
git branch -M main

echo.
echo ============================================================
echo  Widening .gitignore so this stops recurring...
echo ============================================================
(
echo # Secrets ^& credentials
echo client_secret.json
echo *.env
echo .env
echo .env.example
echo key.txt
echo **/key.txt
echo **/*.env.example
echo **/omega_vault.json
echo **/*_secret*.json
echo **/*apikey*
echo **/*api_key*
echo **/*token*.txt
) > .gitignore

git add -A
git commit -q -m "Remove additional leaked secrets, clean history"

echo.
echo ============================================================
echo  Pushing clean history to GitHub...
echo ============================================================
git remote remove origin 2>nul
git remote add origin https://github.com/isearchxsolve/lasthelp.git
git push -f origin main

echo.
echo ============================================================
echo  DONE. Refresh GitHub - if it's still blocked, screenshot
echo  the new error and share it.
echo ============================================================
timeout /t 10
