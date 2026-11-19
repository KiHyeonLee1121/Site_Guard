#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mode="${1:---check}"
if [[ "$mode" != "--check" && "$mode" != "--install" ]]; then
  echo "Usage: $0 [--check|--install]" >&2
  exit 2
fi
if [[ "$(uname -m)" != aarch64 ]] || ! grep -qs '^# R32' /etc/nv_tegra_release; then
  echo "Expected a Jetson with aarch64 L4T R32 (JetPack 4). Run scripts/check_jetson_env.sh." >&2
  exit 2
fi
python3 -c 'import sys; assert sys.version_info[:2] == (3, 6), "Expected JetPack system Python 3.6"'
if [[ "$mode" == "--install" ]]; then
  echo "Installing distro OpenCV, NumPy and Python venv support via apt."
  sudo apt-get install --no-install-recommends python3-opencv python3-numpy python3-venv
  python3 -m venv --system-site-packages .venv-jetson
  .venv-jetson/bin/python -m pip install --disable-pip-version-check -r deployment/jetson/requirements.txt
fi
if [[ -x .venv-jetson/bin/python ]]; then
  py=.venv-jetson/bin/python
else
  py=python3
fi
"$py" -m siteguard --source mock --dry-run --max-frames 30 --database /tmp/siteguard-jetson-install.sqlite3
for package in cv2 numpy serial tensorrt jetson_inference jetson_utils; do
  if ! "$py" -c "import $package" >/dev/null 2>&1; then
    echo "Unavailable for real runs: $package (see docs/JETSON_SETUP.md)"
  fi
done
echo "Mock smoke test passed with $py"
