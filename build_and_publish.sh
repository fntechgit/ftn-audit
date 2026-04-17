#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "[1/5] Cleaning dist/..."
rm -rf dist
mkdir -p dist

echo "[2/5] Making sure build & twine are installed..."
python3 -m pip install --upgrade build twine

echo "[3/5] Building package..."
python3 -m build

echo "[4/5] Uploading to PyPI with twine..."
# If you have TWINE_USERNAME/TWINE_PASSWORD set, this will be non-interactive
python3 -m twine upload dist/*

echo "[5/5] Done ✅"
