<# 
.SYNOPSIS
    AI Video Monetizer - Master Deployment (PowerShell)
    Single-file deployment launcher for the complete automation stack.

.DESCRIPTION
    Runs all prerequisite checks and deployment steps for the AI Video Monetizer.
    Requires: .env configured, Google auth done, API keys added.
    
    Run from PowerShell: .\deploy_all.ps1
    Or right-click -> "Run with PowerShell"
#>

param(
    [switch]$SkipPrereqs,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition

function Write-Log {
    param([string]$Step, [string]$Message, [string]$Status = "info")
    $prefix = switch ($Status) {
        "success" { "[$Step OK]" ; $color = "Green" }
        "warning" { "[$Step WARN]" ; $color = "Yellow" }
        "error"   { "[$Step ERR]" ; $color = "Red" }
        default   { "[$Step]" ; $color = "Cyan" }
    }
    Write-Host "$prefix $Message" -ForegroundColor $color
}

function Write-Header {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  AI VIDEO MONETIZER - MASTER DEPLOYMENT"
    Write-Host "============================================================"
    Write-Host "  Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host "  Project: $ROOT"
    Write-Host ""
}

function Test-Python {
    try {
        $version = python --version 2>&1
        Write-Log "CHECK" "Python found: $version" "success"
        return $true
    } catch {
        Write-Log "CHECK" "Python not found in PATH. Install from python.org" "error"
        return $false
    }
}

function Test-Dotenv {
    try {
        python -c "import dotenv" 2>$null
        Write-Log "CHECK" "python-dotenv available" "success"
        return $true
    } catch {
        Write-Log "CHECK" "python-dotenv not installed. Installing..." "warning"
        try {
            python -m pip install python-dotenv -q
            Write-Log "CHECK" "python-dotenv installed" "success"
            return $true
        } catch {
            Write-Log "CHECK" "Failed to install python-dotenv" "error"
            return $false
        }
    }
}

function Test-GoogleLibs {
    try {
        python -c "import google.auth, google.oauth2, googleapiclient" 2>$null
        Write-Log "CHECK" "Google API libraries available" "success"
        return $true
    } catch {
        Write-Log "CHECK" "Google API libraries not installed. Installing..." "warning"
        try {
            python -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client -q
            Write-Log "CHECK" "Google API libraries installed" "success"
            return $true
        } catch {
            Write-Log "CHECK" "Failed to install Google API libraries" "error"
            return $false
        }
    }
}

function Load-EnvFile {
    $envPath = Join-Path $ROOT ".env"
    if (-not (Test-Path $envPath)) {
        Write-Log "CHECK" ".env file NOT found at $envPath" "error"
        Write-Host "Create it from template:" -ForegroundColor Yellow
        Write-Host "  Copy-Item .env.example .env" -ForegroundColor Yellow
        Write-Host "Then fill in all required values (see ENV_CONFIGURATION_GUIDE.md)" -ForegroundColor Yellow
        return $false
    }
    Write-Log "CHECK" ".env file exists" "success"
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)\s*=\s*(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") {
                $value = $matches[1]
            }
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    return $true
}

function Validate-EnvVars {
    $allOk = $true
    
    $sheetId = $env:GOOGLE_SHEETS_CONTENT_PIPELINE_ID
    if (-not $sheetId -or $sheetId -eq "your_sheet_id_here") {
        Write-Log "CHECK" "GOOGLE_SHEETS_CONTENT_PIPELINE_ID missing or placeholder" "error"
        $allOk = $false
    } else {
        Write-Log "CHECK" "Google Sheet ID configured" "success"
    }
    
    $driveId = $env:GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID
    if (-not $driveId -or $driveId -eq "your_drive_folder_id_here") {
        Write-Log "CHECK" "GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID missing or placeholder" "error"
        $allOk = $false
    } else {
        Write-Log "CHECK" "Drive folder IDs configured" "success"
    }
    
    $files = @(
        @("config\video_prompts.json", "30-day matrix JSON"),
        @("content\ebook_manuscript.md", "E-book manuscript"),
        @("content\texting_framework.md", "Texting framework")
    )
    
    foreach ($file in $files) {
        $path = Join-Path $ROOT $file[0]
        if (-not (Test-Path $path)) {
            Write-Log "CHECK" "$($file[1]) missing: $($file[0])" "error"
            $allOk = $false
        } else {
            Write-Log "CHECK" "$($file[1]) exists" "success"
        }
    }
    
    $tokenPath = Join-Path $env:USERPROFILE ".hermes\google_token.json"
    if (-not (Test-Path $tokenPath)) {
        Write-Log "CHECK" "Google OAuth token NOT found at $tokenPath" "warning"
        Write-Log "CHECK" "Run Google auth first (see README.md Section 1)" "warning"
        $allOk = $false
    } else {
        Write-Log "CHECK" "Google OAuth token found" "success"
    }
    
    return $allOk
}

function Run-PythonScript {
    param([string]$Script, [string]$Description)
    Write-Log "DEPLOY" "$Description..."
    $scriptPath = Join-Path $ROOT "scripts" $Script
    $result = python $scriptPath 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Log "DEPLOY" "$Description failed (exit $exitCode)" "error"
        if ($Verbose) { Write-Host $result -ForegroundColor Red }
        exit $exitCode
    }
    Write-Log "DEPLOY" "$Description completed" "success"
    if ($Verbose) { Write-Host $result -ForegroundColor Green }
}

function Verify-JsonFile {
    param([string]$File, [string]$Description)
    Write-Log "DEPLOY" "Validating $Description..."
    $filePath = Join-Path $ROOT $File
    try {
        $content = Get-Content $filePath -Raw
        $data = $content | ConvertFrom-Json
        Write-Log "DEPLOY" "$Description JSON valid" "success"
        return $true
    } catch {
        Write-Log "DEPLOY" "$Description validation failed: $_" "error"
        return $false
    }
}

function Print-Summary {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  DEPLOYMENT SUMMARY"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "COMPLETED:" -ForegroundColor Cyan
    Write-Host "  - .env.example + README.md created"
    Write-Host "  - 30-day content matrix (config\video_prompts.json)"
    Write-Host "  - E-book manuscript (content\ebook_manuscript.md)"
    Write-Host "  - Texting framework (content\texting_framework.md)"
    Write-Host "  - Google Sheets population script (scripts\populate_sheet.py)"
    Write-Host "  - Make.com scenario blueprint (config\make_scenario.json)"
    Write-Host "  - ManyChat flow blueprint (config\manychat_flow.json)"
    Write-Host "  - Gumroad setup script (scripts\setup_gumroad.py)"
    Write-Host ""
    Write-Host "MANUAL STEPS REQUIRED:" -ForegroundColor Yellow
    Write-Host "  1. Google OAuth: Run auth flow (see README Section 1)"
    Write-Host "  2. Create Drive folders + Sheet -> Add IDs to .env"
    Write-Host "  3. Run: python scripts\populate_sheet.py"
    Write-Host "  4. Add API keys to .env (Runway/Luma/Kling, Make.com, ManyChat, Gumroad)"
    Write-Host "  5. Run: python scripts\setup_gumroad.py"
    Write-Host "  6. Import Make.com scenario (config\make_scenario.json)"
    Write-Host "  7. Build ManyChat flow (config\manychat_flow.json)"
    Write-Host "  8. Connect ManyChat button -> Gumroad Blueprint URL"
    Write-Host "  9. Activate Make.com scenario (daily 9 AM)"
    Write-Host "  10. Test end-to-end: Comment 'MAGNETIC' -> DM -> Purchase"
    Write-Host ""
    Write-Host "KEY FILES:" -ForegroundColor Cyan
    Write-Host "  Config: $ROOT\.env"
    Write-Host "  Sheet:  https://docs.google.com/spreadsheets/d/$env:GOOGLE_SHEETS_CONTENT_PIPELINE_ID/edit"
    Write-Host "  Drive:  https://drive.google.com/drive/folders/$env:GOOGLE_DRIVE_ROOT_FOLDER_ID"
    Write-Host ""
    Write-Host "REVENUE PROJECTION (from blueprint):" -ForegroundColor White
    Write-Host "  - Blueprint: `$9.99 x ~1000 sales/mo = `$10K/mo"
    Write-Host "  - Order bump (30%): +`$10 x 300 = `$3K/mo"
    Write-Host "  - Masterclass upsell (5%): +`$97 x 50 = `$4.85K/mo"
    Write-Host "  - Total potential: ~`$18K/mo at scale"
    Write-Host ""
}

# ============================================================================
# MAIN
# ============================================================================
Write-Header

if (-not $SkipPrereqs) {
    Write-Log "CHECK" "Verifying prerequisites..."
    
    $checks = @(
        (Test-Python),
        (Test-Dotenv),
        (Test-GoogleLibs),
        (Load-EnvFile),
        (Validate-EnvVars)
    )
    
    if ($checks -contains $false) {
        Write-Log "DEPLOY" "Prerequisites not met. Fix issues above before continuing." "error"
        Write-Host "See README.md and ENV_CONFIGURATION_GUIDE.md for detailed setup." -ForegroundColor Yellow
        exit 1
    }
    
    Write-Log "CHECK" "All prerequisites met! Starting deployment..." "success"
    Write-Host ""
}

# 1. Populate Google Sheet with 30-day matrix
Run-PythonScript "populate_sheet.py" "Populating Google Sheets with 30-day matrix"

# 2. Create Gumroad products
Run-PythonScript "setup_gumroad.py" "Setting up Gumroad products"

# 3. Validate Make.com scenario blueprint
if (-not (Verify-JsonFile "config\make_scenario.json" "Make.com scenario")) { exit 1 }

# 4. Validate ManyChat flow blueprint
if (-not (Verify-JsonFile "config\manychat_flow.json" "ManyChat flow")) { exit 1 }

# Print final summary
Print-Summary

Write-Host "DEPLOYMENT READY! Complete manual steps above." -ForegroundColor Green
exit 0