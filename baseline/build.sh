#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIBRIME="${ROOT}/third_party/librime"
INSTALL="${ROOT}/third_party/install"
DATA="${ROOT}/baseline/data"
JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}"

for tool in git cmake make; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "missing build tool: ${tool}; install the platform build toolchain first" >&2
    exit 1
  }
done

if [[ ! -f "${DATA}/luna_pinyin.dict.yaml" ]]; then
  command -v curl >/dev/null 2>&1 || { echo "curl is required to fetch the Rime dictionary" >&2; exit 1; }
  curl --fail --location --silent --show-error \
    https://raw.githubusercontent.com/rime/rime-luna-pinyin/master/luna_pinyin.dict.yaml \
    -o "${DATA}/luna_pinyin.dict.yaml"
fi
cp "${ROOT}/assets/superpinyin.schema.yaml" "${DATA}/superpinyin.schema.yaml"

if [[ ! -d "${LIBRIME}/.git" ]]; then
  mkdir -p "$(dirname "${LIBRIME}")"
  git clone --recursive https://github.com/rime/librime.git "${LIBRIME}"
fi

mkdir -p "${LIBRIME}/build"
cmake -S "${LIBRIME}" -B "${LIBRIME}/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${INSTALL}" \
  -DBUILD_TEST=OFF
cmake --build "${LIBRIME}/build" --parallel "${JOBS}"
cmake --install "${LIBRIME}/build"

OS="$(uname -s)"
if [[ "${OS}" == "Darwin" ]]; then
  CC="${CC:-clang}"
  "${CC}" -std=c11 -I"${INSTALL}/include" -L"${INSTALL}/lib" \
    -Wl,-rpath,"${INSTALL}/lib" "${ROOT}/baseline/dump_candidates.c" \
    -lrime -o "${ROOT}/baseline/dump_candidates"
elif [[ "${OS}" == "Linux" ]]; then
  CC="${CC:-cc}"
  "${CC}" -std=c11 -I"${INSTALL}/include" -L"${INSTALL}/lib" \
    -Wl,-rpath,"${INSTALL}/lib" "${ROOT}/baseline/dump_candidates.c" \
    -lrime -o "${ROOT}/baseline/dump_candidates"
else
  echo "unsupported platform for librime baseline: ${OS}" >&2
  exit 1
fi

echo BUILD_OK
