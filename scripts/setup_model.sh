#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${SITEGUARD_PYTHON:-python3}" tools/prepare_model.py "$@"
