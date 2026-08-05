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
    call :log_error "CHECK" "Python not found in PATH. Install from python.org"
    exit /b 1
)
echo TRACE: Python check passed
call :log_success "CHECK" "Python found"
python --version
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