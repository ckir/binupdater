#!/usr/bin/env bash
# Portable launcher for WSL / Linux.
# Symlink to ~/.local/bin/binupdater for global access:
#   ln -s "$(readlink -f "$0")" ~/.local/bin/binupdater
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
exec python3 "$(dirname "$SCRIPT")/binupdater.py" "$@"
