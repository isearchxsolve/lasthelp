@echo off
echo === DEBUG START ===
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
echo ROOT=%ROOT%

call :print_header
echo === AFTER HEADER ===
goto :eof

:print_header
echo INSIDE PRINT_HEADER
echo Time: %date% %time%
echo Project: %ROOT%
goto :eof