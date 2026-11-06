#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! command -v python3.12 >/dev/null 2>&1; then
  echo 'Install native arm64 Python 3.12 first (brew install python@3.12).' >&2
  exit 1
fi
exec python3.12 scripts/macos.py setup "$@"
