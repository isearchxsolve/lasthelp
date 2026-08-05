@echo off
echo DEPLOY_ALL.BAT STARTING
echo ROOT=%~dp0
echo ROOT=%ROOT:~0,-1%
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
echo ROOT=%ROOT%

echo Checking .env...
if exist "%ROOT%\.env" (
    echo .env EXISTS
) else (
    echo .env NOT FOUND
)

echo Checking Python...
python --version

echo DEPLOY_ALL.BAT DONE
pause