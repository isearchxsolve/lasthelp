@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  final_secret_scrub.bat
REM  Run this from inside your "lasthelp" folder.
REM  Aggressively strips common API-key patterns from EVERY
REM  tracked text file, then makes one fresh commit and pushes.
REM  No typing needed.
REM =========================================================

echo.
echo ============================================================
echo  Scrubbing key-shaped strings from all text/markdown files...
echo ============================================================

for /r %%f in (*.md *.txt *.json *.py *.ipynb *.yml *.yaml *.env *.env.example) do (
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
echo  Wiping git history and starting one fresh commit...
echo ============================================================
rmdir /s /q .git
git init -q
git branch -M main

git add -A
git commit -q -m "Fresh start: aggressive secret scrub across all files"

echo.
echo ============================================================
echo  Pushing clean history to GitHub...
echo ============================================================
git remote remove origin 2>nul
git remote add origin https://github.com/isearchxsolve/lasthelp.git
git push -f origin main

echo.
echo ============================================================
echo  DONE. Refresh GitHub now.
echo ============================================================
timeout /t 10
