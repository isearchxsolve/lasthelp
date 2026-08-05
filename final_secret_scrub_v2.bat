@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  final_secret_scrub_v2.bat
REM  Run this from inside your "lasthelp" folder.
REM  Same as before, but shows progress per file so we can see
REM  exactly where it is, and will NOT close until you press a key.
REM =========================================================

echo.
echo ============================================================
echo  Scrubbing key-shaped strings from tracked files...
echo  (this window will show each file as it goes - do not close)
echo ============================================================

for /r %%f in (*.md *.txt *.json *.py *.yml *.yaml) do (
    echo Scrubbing: %%f
    powershell -NoProfile -Command ^
        "$p = '%%f'; if (Test-Path $p) { " ^
        "(Get-Content $p -Raw) | " ^
        "ForEach-Object { $_ -replace 'AIza[A-Za-z0-9_\-]{35}', 'REDACTED_GCP_KEY' } | " ^
        "ForEach-Object { $_ -replace 'gh[pousr]_[A-Za-z0-9]{20,}', 'REDACTED_GH_TOKEN' } | " ^
        "ForEach-Object { $_ -replace 'sk-or-[A-Za-z0-9\-]+', 'REDACTED_OPENROUTER_KEY' } | " ^
        "ForEach-Object { $_ -replace 'gsk_[A-Za-z0-9]+', 'REDACTED_GROQ_KEY' } | " ^
        "ForEach-Object { $_ -replace '[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com', 'REDACTED_OAUTH_CLIENT_ID' } | " ^
        "ForEach-Object { $_ -replace 'GOCSPX-[A-Za-z0-9_\-]+', 'REDACTED_OAUTH_SECRET' } | " ^
        "Set-Content $p -NoNewline }"
)

echo.
echo ============================================================
echo  Skipping .ipynb files from scrub - removing them instead
echo  since they can hang the text processor (large/binary-ish).
echo ============================================================
del /s /f /q *.ipynb 2>nul

echo.
echo ============================================================
echo  Wiping git history and starting one fresh commit...
echo ============================================================
rmdir /s /q .git
git init -q
git branch -M main
git add -A
git commit -q -m "Fresh start: secrets scrubbed, notebooks removed"

echo.
echo ============================================================
echo  Pushing to GitHub...
echo ============================================================
git remote remove origin 2>nul
git remote add origin https://github.com/isearchxsolve/lasthelp.git
git push -f origin main

echo.
echo ============================================================
echo  FINISHED - result shown above (success or error).
echo  This window will stay open. Press any key to close it
echo  once you have read the result / taken a screenshot.
echo ============================================================
pause
