#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 model.onnx [output.engine]" >&2
  exit 2
fi
onnx="$1"
output="${2:-${onnx%.onnx}.engine}"
[[ "$onnx" == *.onnx && -f "$onnx" && -f "${onnx%.onnx}.json" ]] || { echo "ONNX and matching JSON required" >&2; exit 2; }
[[ "$output" == *.engine && -d "$(dirname "$output")" ]] || { echo "Expected .engine in an existing directory" >&2; exit 2; }
if [[ "$(uname -m)" != aarch64 ]] || ! grep -qs '^# R32' /etc/nv_tegra_release; then
  echo "Build the engine on the target JetPack 4 Jetson." >&2
  exit 2
fi
trtexec="${SITEGUARD_TRTEXEC:-/usr/src/tensorrt/bin/trtexec}"
if [[ ! -x "$trtexec" ]]; then
  if ! trtexec="$(command -v trtexec)"; then
    echo "trtexec unavailable. Verify the JetPack TensorRT installation." >&2
    exit 2
  fi
fi
help="$("$trtexec" --help 2>&1 || true)"
if [[ "$help" != *--workspace* || "$help" != *--skipInference* ]]; then
  echo "This script expects the TensorRT 8 trtexec workspace and skipInference options." >&2
  exit 2
fi
python3 - "$onnx" <<'PY'
import hashlib, json, sys
from pathlib import Path
path = Path(sys.argv[1])
metadata = json.loads(path.with_suffix(".json").read_text())
if metadata.get("format") != "yolo11-raw-v1" or metadata.get("onnx_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
    sys.exit("ONNX and model metadata checksum do not match")
PY
partial="$(mktemp "${output}.part.XXXXXX")"
trap 'rm -f -- "$partial"' EXIT
"$trtexec" --onnx="$onnx" --fp16 "--workspace=${SITEGUARD_TRT_WORKSPACE_MB:-512}" --skipInference "--saveEngine=$partial"
[[ -s "$partial" ]]
mv -- "$partial" "$output"
echo "Engine written to $output"
