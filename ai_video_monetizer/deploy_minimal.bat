@echo off
echo === DEPLOY_ALL MINIMAL ===
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

set "PREFIX_INFO=[INFO]"
set "PREFIX_SUCCESS=[OK]"
set "PREFIX_WARNING=[WARN]"
set "PREFIX_ERROR=[ERR]"

call :print_header
call :main
goto :eof

:print_header
echo.
echo ============================================================
echo   AI VIDEO MONETIZER - MASTER DEPLOYMENT
echo ============================================================
echo Time: %date% %time%
echo Project: %ROOT%
echo.
goto :eof

:main
call :log_info "CHECK" "Verifying prerequisites..."
call :check_python
call :check_dotenv
call :check_google_auth
call :check_env_file
call :load_env
call :validate_env_vars
if errorlevel 1 exit /b 1
call :log_success "CHECK" "All prerequisites met!"
call :print_summary
call :log_success "DEPLOY" "DEPLOYMENT READY!"
goto :eof

:check_python
python --version >nul 2>&1
if errorlevel 1 (call :log_error "CHECK" "Python not found" & exit /b 1)
call :log_success "CHECK" "Python found"
python --version
goto :eof

:check_dotenv
python -c "import dotenv" >nul 2>&1
if errorlevel 1 (
    call :log_warning "CHECK" "python-dotenv not installed. Installing..."
    python -m pip install python-dotenv -q
    if errorlevel 1 (call :log_error "CHECK" "Failed to install python-dotenv" & exit /b 1)
    call :log_success "CHECK" "python-dotenv installed"
) else (call :log_success "CHECK" "python-dotenv available")
goto :eof

:check_google_auth
python -c "import google.auth, google.oauth2, googleapiclient" >nul 2>&1
if errorlevel 1 (
    call :log_warning "CHECK" "Google API libraries not installed. Installing..."
    python -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client -q
    if errorlevel 1 (call :log_error "CHECK" "Failed to install Google API libraries" & exit /b 1)
    call :log_success "CHECK" "Google API libraries installed"
) else (call :log_success "CHECK" "Google API libraries available")
goto :eof

:check_env_file
if not exist "%ROOT%\.env" (call :log_error "CHECK" ".env not found" & exit /b 1)
call :log_success "CHECK" ".env file exists"
goto :eof

:load_env
for /f "usebackq tokens=1,2 delims==" %%a in ("%ROOT%\.env") do (set "%%a=%%b")
goto :eof

:validate_env_vars
set "ALL_OK=1"
if "%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%"=="" (call :log_error "CHECK" "Sheet ID empty" & set "ALL_OK=0")
if "%GOOGLE_SHEETS_CONTENT_PIPELINE_ID%"=="your_sheet_id_here" (call :log_error "CHECK" "Sheet ID placeholder" & set "ALL_OK=0")
if "%GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID%"=="" (call :log_error "CHECK" "Drive ID empty" & set "ALL_OK=0")
if "%GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID%"=="your_drive_folder_id_here" (call :log_error "CHECK" "Drive ID placeholder" & set "ALL_OK=0")
if not exist "%ROOT%\config\video_prompts.json" (call :log_error "CHECK" "JSON missing" & set "ALL_OK=0")
if not exist "%ROOT%\content\ebook_manuscript.md" (call :log_error "CHECK" "Ebook missing" & set "ALL_OK=0")
if not exist "%ROOT%\content\texting_framework.md" (call :log_error "CHECK" "Framework missing" & set "ALL_OK=0")
set "TOKEN_PATH=%USERPROFILE%\.hermes\google_token.json"
if not exist "%TOKEN_PATH%" (call :log_warning "CHECK" "Token not found" & set "ALL_OK=0")
if "%ALL_OK%"=="0" (call :log_error "DEPLOY" "Prerequisites not met" & exit /b 1)
goto :eof

:print_summary
echo.
echo DEPLOYMENT SUMMARY
echo Config: %ROOT%\.env
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