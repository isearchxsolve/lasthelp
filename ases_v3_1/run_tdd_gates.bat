@echo off
REM =============================================================================
REM ASES TDD Gate Runner (Windows)
REM Runs smoke, syntax, and integration gates in sequence and reports status
REM Usage: run_tdd_gates.bat [smoke|syntax|integration|all]
REM =============================================================================

setlocal enabledelayedexpansion

set MODE=%~1
if "%MODE%"=="" set MODE=all

echo ========================================
echo ASES TDD Gate Suite
echo Mode: %MODE%
echo ========================================

set PASSED=0
set FAILED=0
set TOTAL=0

if /I "%MODE%"=="all" (
    call :smoke_gate
    call :syntax_gate
    call :integration_gate
    set TOTAL=3
) else if /I "%MODE%"=="smoke" (
    call :smoke_gate
    set TOTAL=1
) else if /I "%MODE%"=="syntax" (
    call :syntax_gate
    set TOTAL=1
) else if /I "%MODE%"=="integration" (
    call :integration_gate
    set TOTAL=1
) else (
    echo ERROR: Unknown gate "%MODE%"
    echo Usage: run_tdd_gates.bat [smoke^|syntax^|integration^|all]
    exit /b 1
)

echo.
echo ========================================
echo GATE SUMMARY
echo Total Gates Run: %TOTAL%
echo Passed: %PASSED%
echo Failed: %FAILED%
echo ========================================

if %FAILED% equ 0 (
    echo STATUS: ALL GATES PASSED
    exit /b 0
) else (
    echo STATUS: SOME GATES FAILED
    exit /b 1
)

:smoke_gate
echo.
echo ==================== SMOKE GATE ====================
echo Running smoke gate tests...
python -m pytest tests/test_smoke_gate.py -v --tb=short --no-cov
if !ERRORLEVEL! equ 0 (
    echo [PASS] Smoke gate completed
    set /a PASSED+=1
) else (
    echo [FAIL] Smoke gate failed
    set /a FAILED+=1
)
goto :eof

:syntax_gate
echo.
echo ==================== SYNTAX GATE ====================
echo Running syntax gate tests...
python -m pytest tests/test_syntax_gate.py -v --tb=short --no-cov
if !ERRORLEVEL! equ 0 (
    echo [PASS] Syntax gate completed
    set /a PASSED+=1
) else (
    echo [FAIL] Syntax gate failed
    set /a FAILED+=1
)
goto :eof

:integration_gate
echo.
echo ==================== INTEGRATION GATE ====================
echo Running integration E2E gate tests...
python -m pytest tests/test_integration_e2e.py -v --tb=short
if !ERRORLEVEL! equ 0 (
    echo [PASS] Integration gate completed
    set /a PASSED+=1
) else (
    echo [FAIL] Integration gate failed
    set /a FAILED+=1
)
goto :eof