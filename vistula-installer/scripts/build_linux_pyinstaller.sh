#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PY=${PYTHON:-python}

PYINSTALLER=("pyinstaller")
if ! command -v pyinstaller >/dev/null 2>&1; then
  if "$PY" -c "import PyInstaller" >/dev/null 2>&1; then
    PYINSTALLER=("$PY" -m PyInstaller)
  else
    echo "pyinstaller not found. Install it first (example):"
    echo "  $PY -m pip install --user pyinstaller"
    exit 2
  fi
fi

# Bundle i18n assets so the binary is self-contained.
"${PYINSTALLER[@]}" \
  --clean \
  --noconfirm \
  --name vistula-installer \
  --onefile \
  --add-data "assets:assets" \
  vistula_installer/__main__.py

echo "Built: dist/vistula-installer"
