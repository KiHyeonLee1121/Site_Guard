#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test_binary="$(mktemp)"
trap 'rm -f -- "$test_binary"' EXIT
"${CXX:-c++}" -std=c++11 -Wall -Wextra -Werror -I tests/firmware tests/firmware/test_protocol.cpp -o "$test_binary"
"$test_binary"
