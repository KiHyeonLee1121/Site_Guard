#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/check_jetson_env.sh
exec ./deployment/jetson/install.sh "$@"
