#!/usr/bin/env bash
set -euo pipefail
if [[ $# == 0 ]]; then echo "Usage: $0 /absolute/path/dog.mp4 [SiteGuard options]" >&2; exit 2; fi
video="$(realpath "$1")"
shift
cd "$(dirname "$0")/.."
exec "${SITEGUARD_PYTHON:-python3}" -m siteguard --source video --video "$video" "$@"
