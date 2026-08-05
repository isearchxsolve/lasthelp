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
    echo TRACE: Loaded %%a=%%b
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