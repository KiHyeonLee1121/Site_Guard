#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
py="${SITEGUARD_PYTHON:-.venv-jetson/bin/python}"
if [[ ! -x "$py" ]] && ! command -v "$py" >/dev/null; then
  echo "Jetson venv unavailable. Run scripts/bootstrap_jetson.sh --install or set SITEGUARD_PYTHON." >&2
  exit 2
fi
exec "$py" -m siteguard --config config/jetson.yaml --source camera "$@"
