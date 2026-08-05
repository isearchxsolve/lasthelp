@echo off
REM ============================================================================
REM AI VIDEO MONETIZER - MASTER DEPLOYMENT (Windows)
REM Single-file deployment launcher for the complete automation stack.
REM ============================================================================

setlocal enabledelayedexpansion

REM Project root (directory of this script)
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

REM Output prefixes
set "PREFIX_INFO=[INFO]"
set "PREFIX_SUCCESS=[OK]"
set "PREFIX_WARNING=[WARN]"
set "PREFIX_ERROR=[ERR]"

REM ============================================================================
REM Entry point
REM ============================================================================
call :print_header
call :main
goto :eof

REM ============================================================================
REM Main deployment flow
REM ============================================================================
:main
call :log_info "CHECK" "Verifying prerequisites..."

call :check_python
call :check_dotenv
call :check_google_auth
call :check_env_file
call :load_env
call :validate_env_vars

if errorlevel 1 exit /b 1

call :log_success "CHECK" "All prerequisites met! Starting deployment..."
echo.

REM 1. Populate Google Sheet with 30-day matrix
call :run_python_script "populate_sheet.py" "Populating Google Sheets with 30-day matrix"

REM 2. Create Gumroad products
call :run_python_script "setup_gumroad.py" "Setting up Gumroad products"

REM 3. Validate Make.com scenario blueprint
call :verify_json "config\make_scenario.json" "Make.com scenario"

REM 4. Validate ManyChat flow blueprint
call :verify_json "config\manychat_flow.json" "ManyChat flow"

REM Print final summary
call :print_summary

call :log_success "DEPLOY" "DEPLOYMENT READY! Complete manual steps above."
exit /b 0

REM ============================================================================
REM Helper: Logging
REM ============================================================================
:log_info
echo %PREFIX_INFO% [%1] %2
goto :eof

:log_success
echo %PREFIX_SUCCESS% [%1] %2
goto :eof

:log_warning
echo %PREFIX_WARNING% [%1] %2
goto :eof

:log_error
echo %PREFIX_ERROR% [%1] %2
goto :eof

REM ============================================================================
REM Helper: Print header
REM ============================================================================
:print_header
echo.
echo ============================================================
echo   AI VIDEO MONETIZER - MASTER DEPLOYMENT
echo ============================================================
echo Time: %date% %time%
echo Project: %ROOT%
echo.
goto :eof

REM ============================================================================
REM Check: Python
REM ============================================================================
:check_python
python --version >nul 2>&1
if errorlevel 1 (
    call :log_error "CHECK" "Python not found in PATH. Install from python.org"
    exit /b 1
)
call :log_success "CHECK" "Python found"
python --version
goto :eof

REM ============================================================================
REM Check: python-dotenv
REM ============================================================================
:check_dotenv
python -c "import dotenv" >nul 2>&1
if errorlevel 1 (
    call :log_warning "CHECK" "python-dotenv not installed. Installing..."
    python -m pip install python-dotenv -q
    if errorlevel 1 (
        call :log_error "CHECK" "Failed to install python-dotenv"
        exit /b 1
    )
    call :log_success "CHECK" "python-dotenv installed"
) else (
    call :log_success "CHECK" "python-dotenv available"
)
goto :eof

REM ============================================================================
REM Check: Google API libraries
REM ============================================================================
:check_google_auth
python -c "import google.auth, google.oauth2, googleapiclient" >nul 2>&1
if errorlevel 1 (
    call :log_warning "CHECK" "Google API libraries not installed. Installing..."
    python -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client -q
    if errorlevel 1 (
        call :log_error "CHECK" "Failed to install Google API libraries"
        exit /b 1
    )
    call :log_success "CHECK" "Google API libraries installed"
) else (
    call :log_success "CHECK" "Google API libraries available"
)
goto :eof

REM ============================================================================
REM Check: .env file exists
REM ============================================================================
:check_env_file
if not exist "%ROOT%\.env" (
    call :log_error "CHECK" ".env file NOT found"
    echo.
    echo Create it from template:
    echo   copy .env.example .env
    echo.
    echo Then fill in all required values (see ENV_CONFIGURATION_GUIDE.md)
    exit /b 1
)
call :log_success "CHECK" ".env file exists"
goto :eof

REM ============================================================================
REM Load .env into environment variables
REM ============================================================================
:load_env
for /f "usebackq tokens=1,2 delims==" %%a in ("%ROOT%\.env") do (
    set "%%a=%%b"
)
goto :eof

REM ============================================================================
REM Validate required .env variables and files
REM ============================================================================
:validate_env_vars
set "ALL_OK=1"

if "%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%"=="" (
    call :log_error "CHECK" "GOOGLE_SHEETS_CONTENT_PIPELINE_ID not set in .env"
    set "ALL_OK=0"
) else if "%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%"=="your_sheet_id_here" (
    call :log_error "CHECK" "GOOGLE_SHEETS_CONTENT_PIPELINE_ID still has placeholder value"
    set "ALL_OK=0"
) else (
    call :log_success "CHECK" "Google Sheet ID configured"
)

if "%GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID%"=="" (
    call :log_error "CHECK" "GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID not set in .env"
    set "ALL_OK=0"
) else if "%GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID%"=="your_drive_folder_id_here" (
    call :log_error "CHECK" "GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID still has placeholder value"
    set "ALL_OK=0"
) else (
    call :log_success "CHECK" "Drive folder IDs configured"
)

if not exist "%ROOT%\config\video_prompts.json" (
    call :log_error "CHECK" "30-day matrix JSON missing: config\video_prompts.json"
    set "ALL_OK=0"
) else (
    call :log_success "CHECK" "30-day matrix JSON exists"
)

if not exist "%ROOT%\content\ebook_manuscript.md" (
    call :log_error "CHECK" "E-book manuscript missing: content\ebook_manuscript.md"
    set "ALL_OK=0"
) else (
    call :log_success "CHECK" "E-book manuscript exists"
)

if not exist "%ROOT%\content\texting_framework.md" (
    call :log_error "CHECK" "Texting framework missing: content\texting_framework.md"
    set "ALL_OK=0"
) else (
    call :log_success "CHECK" "Texting framework exists"
)

REM Check Google OAuth token
set "TOKEN_PATH=%USERPROFILE%\.hermes\google_token.json"
if not exist "%TOKEN_PATH%" (
    call :log_warning "CHECK" "Google OAuth token NOT found at %TOKEN_PATH%"
    call :log_warning "CHECK" "Run Google auth first (see README.md Section 1)"
    set "ALL_OK=0"
) else (
    call :log_success "CHECK" "Google OAuth token found"
)

if "%ALL_OK%"=="0" (
    echo.
    call :log_error "DEPLOY" "Prerequisites not met. Fix issues above before continuing."
    echo See README.md and ENV_CONFIGURATION_GUIDE.md for detailed setup.
    exit /b 1
)

goto :eof

REM ============================================================================
REM Run a Python deployment script
REM ============================================================================
:run_python_script
set "SCRIPT=%1"
set "DESC=%2"
call :log_info "DEPLOY" "%DESC%..."
python "%ROOT%\scripts\%SCRIPT%"
if errorlevel 1 (
    call :log_error "DEPLOY" "%DESC% failed"
    exit /b 1
)
call :log_success "DEPLOY" "%DESC% completed"
goto :eof

REM ============================================================================
REM Verify JSON file is valid
REM ============================================================================
:verify_json
set "FILE=%1"
set "DESC=%2"
call :log_info "DEPLOY" "Validating %DESC%..."
python -c "import json,sys; f=open(r'%ROOT%\%FILE%'); json.load(f); print('OK: %DESC% valid'); f.close()" 2>&1
if errorlevel 1 (
    call :log_error "DEPLOY" "%DESC% validation failed"
    exit /b 1
)
call :log_success "DEPLOY" "%DESC% JSON valid"
goto :eof

REM ============================================================================
REM Print deployment summary
REM ============================================================================
:print_summary
echo.
echo ============================================================
echo   DEPLOYMENT SUMMARY
echo ============================================================
echo.
echo COMPLETED:
echo   - .env.example + README.md created
echo   - 30-day content matrix (config\video_prompts.json)
echo   - E-book manuscript (content\ebook_manuscript.md)
echo   - Texting framework (content\texting_framework.md)
echo   - Google Sheets population script (scripts\populate_sheet.py)
echo   - Make.com scenario blueprint (config\make_scenario.json)
echo   - ManyChat flow blueprint (config\manychat_flow.json)
echo   - Gumroad setup script (scripts\setup_gumroad.py)
echo.
echo MANUAL STEPS REQUIRED:
echo   1. Google OAuth: Run auth flow (see README Section 1)
echo   2. Create Drive folders + Sheet - Add IDs to .env
echo   3. Run: python scripts\populate_sheet.py
echo   4. Add API keys to .env (Runway/Luma/Kling, Make.com, ManyChat, Gumroad)
echo   5. Run: python scripts\setup_gumroad.py
echo   6. Import Make.com scenario (config\make_scenario.json)
echo   7. Build ManyChat flow (config\manychat_flow.json)
echo   8. Connect ManyChat button - Gumroad Blueprint URL
echo   9. Activate Make.com scenario (daily 9 AM)
echo   10. Test end-to-end: Comment 'MAGNETIC' - DM - Purchase
echo.
echo KEY FILES:
echo   Config: %ROOT%\.env
echo   Sheet:  https://docs.google.com/spreadsheets/d/%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%/edit
echo   Drive:  https://drive.google.com/drive/folders/%GOOGLE_DRIVE_ROOT_FOLDER_ID%
echo.
echo REVENUE PROJECTION (from blueprint):
echo   - Blueprint: $9.99 x ~1000 sales/mo = $10K/mo
echo   - Order bump (30%%): +$10 x 300 = $3K/mo
echo   - Masterclass upsell (5%%): +$97 x 50 = $4.85K/mo
echo   - Total potential: ~$18K/mo at scale
echo.
goto :eof