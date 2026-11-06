#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv-macos/bin/python ]]; then
  echo 'Run bash Setup-macOS.sh first.' >&2
  exit 1
fi
exec .venv-macos/bin/python scripts/macos.py start "$@"
