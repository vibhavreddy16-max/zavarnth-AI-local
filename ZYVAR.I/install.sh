#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Zyvarnth requires Python 3.11 or newer. Set PYTHON_BIN to a supported interpreter.")
if sys.version_info >= (3, 14):
    raise SystemExit("This release supports Python 3.11–3.13.")
print(f"Using Python {sys.version.split()[0]}")
PY

"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[desktop,notify]'
.venv/bin/python -m playwright install chromium
printf '%s\n' "Install complete. Run: .venv/bin/python main.py"

