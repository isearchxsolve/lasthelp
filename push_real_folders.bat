@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  push_real_folders.bat
REM  Run this from inside your "lasthelp" folder.
REM  Removes any leftover *_engineering_marvel.zip files,
REM  adds your real project folders, commits, and pushes.
REM  No typing needed.
REM =========================================================

echo.
echo ============================================================
echo  Removing any zip files sitting in this repo...
echo ============================================================
for %%f in (*_engineering_marvel.zip) do (
    echo Deleting %%f
    del /f /q "%%f"
)
for %%f in (*.zip) do (
    echo Deleting %%f
    del /f /q "%%f"
)

echo.
echo ============================================================
echo  Staging real project folders...
echo ============================================================
git add -A

echo.
echo ============================================================
echo  Committing...
echo ============================================================
git commit -q -m "Replace zipped folders with real project files"

echo.
echo ============================================================
echo  Pushing to GitHub...
echo ============================================================
git push origin main

echo.
echo ============================================================
echo  DONE. Check GitHub - you should now see real folders,
echo  not zip files.
echo ============================================================
timeout /t 10
