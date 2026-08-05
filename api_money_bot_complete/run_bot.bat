@echo off
REM API Money Bot v3.0 — Windows Launcher
REM ========================================
REM Menu-driven interface for running the bot

title API Money Bot v3.0
color 0A

:MENU
cls
echo ═══════════════════════════════════════════════════════════
echo   API MONEY BOT v3.0 — PAYMENT AUTOMATION EDITION
echo ═══════════════════════════════════════════════════════════
echo.
echo   [1] Health Check (validate credentials)
echo   [2] Safe Monitoring Run (read-only, no money moves)
echo   [3] Revenue Summary
echo   [4] Run API Key Harvester (all platforms)
echo   [5] Run API Key Harvester (specific platforms)
echo   [6] Show Harvested Keys
echo   [7] Single Platform Run (interactive)
echo   [8] Live Action (requires LIVE_MODE=true)
echo   [9] Exit
echo.
echo ═══════════════════════════════════════════════════════════
set /p CHOICE="Select option [1-9]: "

if "%CHOICE%"=="1" goto HEALTH
if "%CHOICE%"=="2" goto MONITOR
if "%CHOICE%"=="3" goto SUMMARY
if "%CHOICE%"=="4" goto HARVEST_ALL
if "%CHOICE%"=="5" goto HARVEST_SPECIFIC
if "%CHOICE%"=="6" goto SHOW_KEYS
if "%CHOICE%"=="7" goto SINGLE_PLATFORM
if "%CHOICE%"=="8" goto LIVE_ACTION
if "%CHOICE%"=="9" goto EXIT

echo Invalid option. Press any key to continue...
pause >nul
goto MENU

:HEALTH
echo.
echo Running Health Check...
echo.
python src/api_money_bot_v3.py --health
echo.
pause
goto MENU

:MONITOR
echo.
echo Running Safe Monitoring (LIVE_MODE=false)...
echo.
python src/api_money_bot_v3.py
echo.
pause
goto MENU

:SUMMARY
echo.
echo Generating Revenue Summary...
echo.
python src/api_money_bot_v3.py --summary
echo.
pause
goto MENU

:HARVEST_ALL
echo.
echo Harvesting ALL platform keys...
echo.
python api_key_harvester/main.py
echo.
pause
goto MENU

:HARVEST_SPECIFIC
echo.
set /p PLATFORMS="Enter platform names (space-separated, e.g. binance coinbase github): "
python api_key_harvester/main.py --platforms %PLATFORMS%
echo.
pause
goto MENU

:SHOW_KEYS
echo.
echo Showing Harvested Keys...
echo.
python api_key_harvester/main.py --show
echo.
pause
goto MENU

:SINGLE_PLATFORM
echo.
echo Available platforms:
echo   binance coinbase kucoin bybit okx
echo   upwork freelancer reddit
echo   shutterstock adobestock pond5
echo   gumroad etsy ebay stripe
echo   shopify printful printify
echo   youtube medium openai anthropic replicate
echo   razorpay wise paypal
echo   toloka clickworker remotasks
echo.
set /p PLATFORM="Enter platform name: "
python src/api_money_bot_v3.py --platform %PLATFORM%
echo.
pause
goto MENU

:LIVE_ACTION
echo.
echo ⚠️  WARNING: This requires LIVE_MODE=true in .env
echo ⚠️  No money moves unless LIVE_MODE=true and category flags are enabled!
echo.
echo Available actions per platform:
echo   Binance: execute_trade '{"symbol":"BTCUSDT","side":"BUY","quantity":0.001}'
echo   (Check platform class for more actions)
echo.
set /p PLATFORM="Enter platform: "
set /p ACTION="Enter action method: "
set /p ARGS="Enter JSON args (optional): "
if "%ARGS%"=="" (
    LIVE_MODE=true python src/api_money_bot_v3.py --platform %PLATFORM% --action %ACTION%
) else (
    LIVE_MODE=true python src/api_money_bot_v3.py --platform %PLATFORM% --action %ACTION% --args "%ARGS%"
)
echo.
pause
goto MENU

:EXIT
echo.
echo Goodbye!
timeout /t 2 >nul
exit /b