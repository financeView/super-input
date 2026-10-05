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
  -DBUILD_TEST=OFF \
  -DBUILD_DATA=ON
cmake --build "${LIBRIME}/build" --parallel "${JOBS}"
cmake --install "${LIBRIME}/build"

# `use_preset_vocabulary: true` in luna_pinyin expects the shared essay list.
# The current upstream source keeps minimal runtime data under data/minimal.
SHARED_DATA="${INSTALL}/share/rime-data"
mkdir -p "${SHARED_DATA}"
for preset in essay.txt symbols.yaml; do
  if [[ -f "${LIBRIME}/data/minimal/${preset}" ]]; then
    cp "${LIBRIME}/data/minimal/${preset}" "${SHARED_DATA}/${preset}"
  fi
done

OPENCC_DATA_DIR="${OPENCC_DATA_DIR:-}"
if [[ -z "${OPENCC_DATA_DIR}" ]]; then
  for candidate in /usr/share/opencc /opt/homebrew/share/opencc /usr/local/share/opencc; do
    if [[ -f "${candidate}/t2s.json" ]]; then
      OPENCC_DATA_DIR="${candidate}"
      break
    fi
  done
fi
if [[ -z "${OPENCC_DATA_DIR}" && "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  candidate="$(brew --prefix opencc 2>/dev/null)/share/opencc"
  [[ -f "${candidate}/t2s.json" ]] && OPENCC_DATA_DIR="${candidate}"
fi
if [[ -z "${OPENCC_DATA_DIR}" || ! -f "${OPENCC_DATA_DIR}/t2s.json" ]]; then
  echo "OpenCC data not found; install opencc or set OPENCC_DATA_DIR" >&2
  exit 1
fi
shopt -s nullglob
opencc_files=("${OPENCC_DATA_DIR}"/*.json "${OPENCC_DATA_DIR}"/*.ocd2)
if (( ${#opencc_files[@]} == 0 )); then
  echo "no OpenCC data files found in ${OPENCC_DATA_DIR}" >&2
  exit 1
fi
cp "${opencc_files[@]}" "${SHARED_DATA}/"

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
