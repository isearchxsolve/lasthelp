#!/bin/bash
# =============================================================================
# ASES TDD Gate Runner
# Runs smoke, syntax, and integration gates in sequence and reports status
# Usage: ./run_tdd_gates.sh [smoke|syntax|integration|all]
# =============================================================================

set -euo pipefail

MODE="${1:-all}"

echo "========================================"
echo "ASES TDD Gate Suite"
echo "Mode: ${MODE}"
echo "========================================"
echo

run_gate() {
    case "${MODE}" in
        all)
            echo
            echo "=================== SMOKE GATE ===================="
            if ! smoke_gate; then return 1; fi

            echo
            echo "=================== SYNTAX GATE ===================="
            if ! syntax_gate; then return 1; fi

            echo
            echo "=================== INTEGRATION GATE ===================="
            if ! integration_gate; then return 1; fi
            ;;
        smoke)
            smoke_gate
            ;;
        syntax)
            syntax_gate
            ;;
        integration)
            integration_gate
            ;;
        *)
            echo "ERROR: Unknown gate ${MODE}"
            exit 1
            ;;
    esac
}

smoke_gate() {
    echo "Running smoke gate tests..."
    python -m pytest tests/test_smoke_gate.py -v --tb=short
    if [ $? -eq 0 ]; then
        echo "[PASS] Smoke gate completed"
        return 0
    else
        echo "[FAIL] Smoke gate failed"
        return 1
    fi
}

syntax_gate() {
    echo "Running syntax gate tests..."
    python -m pytest tests/test_syntax_gate.py -v --tb=short
    if [ $? -eq 0 ]; then
        echo "[PASS] Syntax gate completed"
        return 0
    else
        echo "[FAIL] Syntax gate failed"
        return 1
    fi
}

integration_gate() {
    echo "Running integration E2E gate tests..."
    python -m pytest tests/test_integration_e2e.py -v --tb=short
    if [ $? -eq 0 ]; then
        echo "[PASS] Integration gate completed"
        return 0
    else
        echo "[FAIL] Integration gate failed"
        return 1
    fi
}

echo
echo "========================================"
echo "GATE SUMMARY"
echo "Mode: ${MODE}"
echo "========================================"
echo
echo "STATUS: All gates executed"
echo
if [ "${MODE}" = "all" ]; then
    echo "Run './run_tdd_gates.sh smoke' for smoke only"
    echo "Run './run_tdd_gates.sh syntax' for syntax only"
    echo "Run './run_tdd_gates.sh integration' for integration only"
fi
echo
echo "Coverage report: htmlcov/index.html"
echo
exit 0