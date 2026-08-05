@echo off
echo === TRACE START ===
setlocal enabledelayedexpansion
echo TRACE: After setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
echo TRACE: ROOT=%ROOT%

set "PREFIX_INFO=[INFO]"
set "PREFIX_SUCCESS=[OK]"
set "PREFIX_WARNING=[WARN]"
set "PREFIX_ERROR=[ERR]"
echo TRACE: Prefixes set

call :print_header
echo TRACE: After print_header

call :check_python
echo TRACE: After check_python

call :check_dotenv
echo TRACE: After check_dotenv

call :check_google_auth
echo TRACE: After check_google_auth

call :check_env_file
echo TRACE: After check_env_file

call :load_env
echo TRACE: After load_env

call :validate_env_vars
echo TRACE: After validate_env_vars
echo ALL_OK=%ALL_OK%
goto :eof

:print_header
echo TRACE: Inside print_header
echo.
echo ============================================================
echo   AI VIDEO MONETIZER - MASTER DEPLOYMENT
echo ============================================================
echo Time: %date% %time%
echo Project: %ROOT%
echo.
goto :eof

:check_python
echo TRACE: Inside check_python
python --version >nul 2>&1
if errorlevel 1 (
    echo TRACE: Python check failed
    call :log_error "CHECK" "Python not found"
    exit /b 1
)
echo TRACE: Python check passed
call :log_success "CHECK" "Python found"
python --version
goto :eof

:check_dotenv
echo TRACE: Inside check_dotenv
python -c "import dotenv" >nul 2>&1
echo TRACE: check_dotenv python returned %errorlevel%
if errorlevel 1 (
    echo TRACE: dotenv not found, installing
    call :log_warning "CHECK" "python-dotenv not installed. Installing..."
    python -m pip install python-dotenv -q
    if errorlevel 1 (
        echo TRACE: pip install failed
        call :log_error "CHECK" "Failed to install python-dotenv"
        exit /b 1
    )
    echo TRACE: pip install succeeded
    call :log_success "CHECK" "python-dotenv installed"
) else (
    echo TRACE: dotenv already available
    call :log_success "CHECK" "python-dotenv available"
)
echo TRACE: Leaving check_dotenv
goto :eof

:check_google_auth
echo TRACE: Inside check_google_auth
python -c "import google.auth, google.oauth2, googleapiclient" >nul 2>&1
echo TRACE: check_google_auth python returned %errorlevel%
if errorlevel 1 (
    echo TRACE: google libs not found, installing
    call :log_warning "CHECK" "Google API libraries not installed. Installing..."
    python -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client -q
    if errorlevel 1 (
        echo TRACE: pip install failed
        call :log_error "CHECK" "Failed to install Google API libraries"
        exit /b 1
    )
    echo TRACE: pip install succeeded
    call :log_success "CHECK" "Google API libraries installed"
) else (
    echo TRACE: google libs already available
    call :log_success "CHECK" "Google API libraries available"
)
echo TRACE: Leaving check_google_auth
goto :eof

:check_env_file
echo TRACE: Inside check_env_file
if not exist "%ROOT%\.env" (
    echo TRACE: .env not found
    call :log_error "CHECK" ".env not found"
    exit /b 1
)
echo TRACE: .env exists
call :log_success "CHECK" ".env file exists"
goto :eof

:load_env
echo TRACE: Inside load_env
for /f "usebackq tokens=1,2 delims==" %%a in ("%ROOT%\.env") do (
    set "%%a=%%b"
)
echo TRACE: load_env done
goto :eof

:validate_env_vars
echo TRACE: Inside validate_env_vars
set "ALL_OK=1"
echo TRACE: ALL_OK init

if "%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%"=="" (
    echo TRACE: Sheet ID empty
    call :log_error "CHECK" "Sheet ID empty"
    set "ALL_OK=0"
) else if "%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%"=="your_sheet_id_here" (
    echo TRACE: Sheet ID placeholder
    call :log_error "CHECK" "Sheet ID placeholder"
    set "ALL_OK=0"
) else (
    echo TRACE: Sheet ID OK
    call :log_success "CHECK" "Sheet ID configured"
)
echo TRACE: validate_env_vars done
goto :eof

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