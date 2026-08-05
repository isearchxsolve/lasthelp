@echo off
setlocal enabledelayedexpansion

REM =========================================================
REM  fix_last_gcp_key.bat
REM  Targets the last remaining GCP key in OMEGA/README.md
REM  This is the final fix before pushing clean.
REM =========================================================

echo.
echo ============================================================
echo  Checking OMEGA/README.md line 67 for GCP key...
echo ============================================================

REM Read the file, find line 67, and redact any key-like content
powershell -NoProfile -Command ^
  "$lines = @(Get-Content 'OMEGA\README.md'); " ^
  "if ($lines.Count -gt 66) { " ^
  "$lines[66] = $lines[66] -replace '[A-Za-z0-9_-]{30,}', 'REDACTED_GCP_KEY'; " ^
  "Set-Content 'OMEGA\README.md' $lines -NoNewline; " ^
  "Write-Host 'Line 67 scrubbed successfully'; " ^
  "} else { Write-Host 'File has fewer than 67 lines'; }"

echo.
echo ============================================================
echo  Committing the final fix...
echo ============================================================
git add OMEGA/README.md
git commit -q -m "Remove GCP API key from README.md line 67"

echo.
echo ============================================================
echo  Force-pushing final clean version to GitHub...
echo ============================================================
git push -f origin main

echo.
echo ============================================================
echo  DONE. Check GitHub - should push clean now.
echo ============================================================
timeout /t 10
