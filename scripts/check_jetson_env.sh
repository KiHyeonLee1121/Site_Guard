#!/usr/bin/env bash
set -u
section() {
  local title="$1"
  shift
  printf '\n[%s]\n' "$title"
  "$@" || printf 'Unavailable (exit %s)\n' "$?"
}
section 'L4T' cat /etc/nv_tegra_release
section 'OS' cat /etc/os-release
section 'Architecture' uname -m
section 'Python' "${SITEGUARD_PYTHON:-python3}" --version
section 'Memory' free -h
section 'Disk space' df -h /
section 'CUDA' bash -c 'nvcc --version || /usr/local/cuda/bin/nvcc --version'
section 'TensorRT packages' dpkg-query -W 'libnvinfer*' 'python3-libnvinfer*'
section 'Docker' docker --version
section 'OpenCV and runtime imports' "${SITEGUARD_PYTHON:-python3}" - <<'PY'
from importlib import import_module
import sqlite3
print("SQLite", sqlite3.sqlite_version)
for name in ("cv2", "numpy", "serial", "tensorrt", "jetson_inference", "jetson_utils", "pycuda.driver"):
    try:
        module = import_module(name)
        print(name, getattr(module, "__version__", "available"))
    except Exception as error:
        print(name, "unavailable:", error)
PY
section 'Video/Serial access' bash -c '
shopt -s nullglob
devices=(/dev/video* /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/*)
if (("${#devices[@]}" == 0)); then echo "No video or serial devices found"; fi
for device in "${devices[@]}"; do
  ls -l "$device"
  [[ -r "$device" && -w "$device" ]] && echo "Readable/writable by current user" || echo "Check permissions"
done'
section 'Current groups' id
section 'NVIDIA devices and power mode' bash -c '
ls -l /dev/nvhost-gpu /dev/nvmap 2>/dev/null
if command -v nvpmodel >/dev/null; then nvpmodel -q; fi
if command -v tegrastats >/dev/null; then
  timeout 2s tegrastats --interval 1000
  code=$?
  [[ $code == 0 || $code == 124 ]]
fi'
section 'Network interfaces' ip -brief address
