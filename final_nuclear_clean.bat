@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  final_nuclear_clean.bat
REM  Wipes git history entirely, removes/redacts the README
REM  key from disk, and pushes one completely fresh commit.
REM  This is the absolute final step.
REM =========================================================

echo.
echo ============================================================
echo  FINAL STEP: Wiping ALL git history and starting fresh...
echo ============================================================

REM Remove git completely
rmdir /s /q .git

REM Initialize new repo
git init -q
git branch -M main

REM Fix the README.md to remove/redact the GCP key
echo Redacting GCP key from OMEGA/README.md...
powershell -NoProfile -Command ^
  "$content = Get-Content 'OMEGA\README.md' -Raw; " ^
  "$content = $content -replace 'AIza[A-Za-z0-9_\-]{35}', 'REDACTED_GCP_KEY'; " ^
  "$content = $content -replace '[A-Za-z0-9_\-]{40,}', 'REDACTED_GCP_KEY'; " ^
  "Set-Content 'OMEGA\README.md' $content -NoNewline"

REM Add everything and commit
echo Adding all files...
git add -A

echo Committing...
git commit -q -m "Fresh start: all secrets removed from history"

REM Setup remote and push
echo Connecting to GitHub...
git remote remove origin 2>nul
git remote add origin https://github.com/isearchxsolve/lasthelp.git

echo Force-pushing to GitHub...
git push -f origin main

echo.
echo ============================================================
echo  FINAL PUSH COMPLETE.
echo  If this succeeded, all secrets are now gone from GitHub.
echo  If still blocked, the key format may need a different regex.
echo ============================================================
timeout /t 10
