#!/bin/bash
# Run all tests locally
set -e

echo "=== Running Unit Tests ==="
cd tests/unit
pytest -v

echo ""
echo "=== Running Integration Tests ==="
cd ../integration
pytest -v

echo ""
echo "=== All tests passed ==="
