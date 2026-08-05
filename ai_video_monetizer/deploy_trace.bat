@echo off
echo === DEPLOY_ALL WITH TRACE ===
setlocal enabledelayedexpansion

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

call :main
echo TRACE: After main
pause
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

:main
echo TRACE: Inside main
call :log_info "CHECK" "Verifying prerequisites..."
echo TRACE: After log_info in main
goto :eof

:log_info
echo TRACE: Inside log_info, args: %1 %2
echo %PREFIX_INFO% [%1] %2
echo TRACE: Leaving log_info
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