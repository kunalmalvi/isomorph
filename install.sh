#!/bin/sh
# One step install: creates .venv and installs ISOMORPH into it. Needs only Python 3.9+ and network access for pip's build backend.
# You do not need this to try the app: `python3 ./isomorph serve` runs straight from the checkout with no install.
set -eu
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo "Python 3.9 or newer is required (found: $("$PY" -V 2>&1))." >&2; exit 1; }
"$PY" -m venv .venv
.venv/bin/python -m pip install --quiet -e .
echo
echo "Installed. Start the app with:"
echo "  .venv/bin/isomorph serve"
echo "Check the setup with:  .venv/bin/isomorph doctor"
