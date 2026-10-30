#!/usr/bin/env bash
# 跨平台入口（Git Bash / macOS / Linux）：./aiacting.sh <子命令>
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$HERE/.venv/Scripts/python.exe" ]; then
  exec "$HERE/.venv/Scripts/python.exe" -m aiacting "$@"
elif [ -x "$HERE/.venv/bin/python" ]; then
  exec "$HERE/.venv/bin/python" -m aiacting "$@"
else
  exec python3 -m aiacting "$@"
fi
