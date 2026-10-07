#!/usr/bin/env bash
# Portable launcher for WSL / Linux / macOS.
# Symlink to ~/.local/bin/binupdater for global access:
#   ln -s "$(readlink -f "$0")" ~/.local/bin/binupdater
SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
if command -v readlink >/dev/null 2>&1 && readlink -f "$SCRIPT_SOURCE" >/dev/null 2>&1; then
    SCRIPT="$(readlink -f "$SCRIPT_SOURCE")"
elif command -v realpath >/dev/null 2>&1; then
    SCRIPT="$(realpath "$SCRIPT_SOURCE")"
else
    SCRIPT="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd -P)/$(basename "$SCRIPT_SOURCE")"
fi
SCRIPT_DIR="$(dirname "$SCRIPT")"

# Prefer the project venv (mirrors binupdater.bat), fall back to PATH.
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
else
    PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/binupdater.py" "$@"
