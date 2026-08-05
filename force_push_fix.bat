@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  force_push_fix.bat
REM  Run this from inside your "lasthelp" folder.
REM  Fixes "rejected - fetch first" by force-pushing your
REM  local state to GitHub, overwriting what's there.
REM  No typing needed.
REM =========================================================

echo.
echo ============================================================
echo  Force pushing local repo to GitHub (overwrites remote)...
echo ============================================================
git push origin main --force

echo.
echo ============================================================
echo  DONE. Check GitHub now - refresh the page.
echo ============================================================
timeout /t 10
