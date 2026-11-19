#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -m)" != aarch64 ]] || ! grep -qs '^# R32' /etc/nv_tegra_release; then
  echo "This installer is for Jetson aarch64, L4T R32." >&2
  exit 2
fi
if python3 -c 'from jetson_inference import detectNet; from jetson_utils import cudaFromNumpy' 2>/dev/null; then
  echo "Native inference bindings found. Use scripts/setup_model.sh jetson next."
  exit 0
fi
if [[ ! -x /usr/local/cuda/bin/nvcc ]] && ! command -v nvcc >/dev/null; then
  echo "Install the CUDA toolkit matching the board's JetPack first." >&2
  exit 2
fi
if ! dpkg-query -W -f='${Status}' libnvinfer-dev 2>/dev/null | grep -q 'install ok installed'; then
  echo "Install the JetPack-matched TensorRT development package libnvinfer-dev first." >&2
  exit 2
fi
sudo apt-get install --no-install-recommends build-essential cmake git git-lfs libpython3-dev python3-numpy \
  libglew-dev libgstreamer1.0-dev libgstrtspserver-1.0-dev libglib2.0-dev libsoup2.4-dev libjson-glib-dev \
  libgstreamer-plugins-base1.0-dev libgstreamer-plugins-good1.0-dev libgstreamer-plugins-bad1.0-dev qtbase5-dev
rev=45da40a8f3c180191b269f57f736caaa025b8a69
upstream="$PWD/models/local/jetson-inference-src"
if [[ ! -d "$upstream/.git" ]]; then
  mkdir -p "$PWD/models/local"
  git clone --no-checkout https://github.com/dusty-nv/jetson-inference.git "$upstream"
fi
git -C "$upstream" checkout --detach "$rev"
git -C "$upstream" submodule update --init --recursive
mkdir -p "$upstream/build"
cd "$upstream/build"
cmake -DBUILD_DEPS=NO -DBUILD_INTERACTIVE=NO -DBUILD_EXPERIMENTAL=NO ..
cmake --build . -- -j "${SITEGUARD_BUILD_JOBS:-2}"
sudo cmake --build . --target install
sudo ldconfig
python3 -c 'from jetson_inference import detectNet; from jetson_utils import cudaFromNumpy'
