@echo off
REM ============================================================================
REM AI VIDEO MONETIZER - COMPLETE AUTOMATION RUNNER (Windows)
REM Single batch file: checks prerequisites, then runs the automation daemon.
REM The daemon continuously polls Google Sheets, generates videos, uploads to
REM Drive, posts to social scheduler - replacing Make.com orchestration.
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
REM Main flow: prerequisites -> run automation daemon
REM ============================================================================
:main
call :log_info "CHECK" "Verifying prerequisites..."

call :check_python
call :check_dotenv
call :check_google_auth
call :check_requests
call :check_daemon_script
call :check_env_file
call :load_env
call :validate_env_vars

if errorlevel 1 (
    echo.
    call :log_error "START" "Prerequisites not met. Fix issues above before starting automation."
    echo See README.md and ENV_CONFIGURATION_GUIDE.md for detailed setup.
    pause
    exit /b 1
)

call :log_success "CHECK" "All prerequisites met! Starting automation daemon..."
echo.

REM Run the automation daemon (blocks until Ctrl+C)
call :log_info "DAEMON" "Starting run_automation.py (Press Ctrl+C to stop)..."
python "%ROOT%\scripts\run_automation.py"

REM If we get here, daemon stopped
call :log_info "DAEMON" "Automation daemon stopped."
pause
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
echo   AI VIDEO MONETIZER - COMPLETE AUTOMATION RUNNER
echo ============================================================
echo Time: %date% %time%
echo Project: %ROOT%
echo.
echo This runs the CONTINUOUS AUTOMATION DAEMON that:
echo   1. Polls Google Sheets for Status = "Ready"
echo   2. Generates video via AI API (Runway/Luma/Kling)
echo   3. Uploads to Google Drive (02_Raw_AI_Videos)
echo   4. Updates Sheet with video link
echo   5. Posts to social scheduler (Buffer/Metricool/Later)
echo   6. Loops every %AUTOMATION_POLL_INTERVAL% seconds (default 5 min)
echo.
echo Press Ctrl+C in this window to stop the daemon gracefully.
echo ============================================================
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
REM Check: requests library (for API calls)
REM ============================================================================
:check_requests
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    call :log_warning "CHECK" "requests library not installed. Installing..."
    python -m pip install requests -q
    if errorlevel 1 (
        call :log_error "CHECK" "Failed to install requests"
        exit /b 1
    )
    call :log_success "CHECK" "requests library installed"
) else (
    call :log_success "CHECK" "requests library available"
)
goto :eof

REM ============================================================================
REM Check: run_automation.py exists
REM ============================================================================
:check_daemon_script
if not exist "%ROOT%\scripts\run_automation.py" (
    call :log_error "CHECK" "Automation daemon script not found: scripts\run_automation.py"
    exit /b 1
)
call :log_success "CHECK" "Automation daemon script found"
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

REM Check at least one video API key
set "HAS_VIDEO_API=0"
if not "%RUNWAY_API_KEY%"=="" if not "%RUNWAY_API_KEY%"=="your_runway_api_key_here" (
    call :log_success "CHECK" "Runway API key configured"
    set "HAS_VIDEO_API=1"
)
if not "%LUMA_API_KEY%"=="" if not "%LUMA_API_KEY%"=="your_luma_api_key_here" (
    call :log_success "CHECK" "Luma API key configured"
    set "HAS_VIDEO_API=1"
)
if not "%KLING_API_KEY%"=="" if not "%KLING_API_KEY%"=="your_kling_api_key_here" (
    call :log_success "CHECK" "Kling API key configured"
    set "HAS_VIDEO_API=1"
)
if "%HAS_VIDEO_API%"=="0" (
    call :log_error "CHECK" "No video API key configured! Need at least one: RUNWAY_API_KEY, LUMA_API_KEY, or KLING_API_KEY"
    set "ALL_OK=0"
)

REM Check scheduler config
if "%ACTIVE_SCHEDULER%"=="buffer" (
    if "%BUFFER_ACCESS_TOKEN%"=="" (
        call :log_warning "CHECK" "Buffer scheduler selected but BUFFER_ACCESS_TOKEN not set"
    ) else (
        call :log_success "CHECK" "Buffer scheduler configured"
    )
)
if "%ACTIVE_SCHEDULER%"=="metricool" (
    if "%METRICOOL_API_KEY%"=="" (
        call :log_warning "CHECK" "Metricool scheduler selected but METRICOOL_API_KEY not set"
    ) else (
        call :log_success "CHECK" "Metricool scheduler configured"
    )
)
if "%ACTIVE_SCHEDULER%"=="later" (
    if "%LATER_ACCESS_TOKEN%"=="" (
        call :log_warning "CHECK" "Later scheduler selected but LATER_ACCESS_TOKEN not set"
    ) else (
        call :log_success "CHECK" "Later scheduler configured"
    )
)

if "%ALL_OK%"=="0" (
    exit /b 1
)

goto :eof