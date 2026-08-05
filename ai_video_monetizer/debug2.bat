@echo off
echo === DEPLOY_ALL DEBUG ===
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
echo ROOT=%ROOT%

call :print_header
echo === AFTER HEADER, CALLING MAIN ===
call :main
echo === AFTER MAIN ===
pause
goto :eof

:print_header
echo INSIDE PRINT_HEADER
echo Time: %date% %time%
echo Project: %ROOT%
goto :eof

:main
echo INSIDE MAIN
call :log_info "TEST" "Test message"
echo MAIN DONE
goto :eof

:log_info
echo [INFO] [%1] %2
goto :eof