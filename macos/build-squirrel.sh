#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM_DIR="$ROOT/third_party/squirrel"
PINNED_COMMIT="$(tr -d '[:space:]' < "$ROOT/macos/SQUIRREL_COMMIT")"
PATCH_FILE="$ROOT/macos/patches/squirrel-integration.patch"
SCHEMA_FILE="$ROOT/assets/superpinyin.schema.yaml"
OUTPUT_DIR="$ROOT/dist"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This build must run on macOS with Xcode; current OS is $(uname -s)." >&2
  exit 2
fi
for tool in git make xcodebuild xcrun python3 ditto; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 2; }
done

mkdir -p "$ROOT/third_party"
if [[ ! -d "$UPSTREAM_DIR/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/rime/squirrel.git "$UPSTREAM_DIR"
  git -C "$UPSTREAM_DIR" fetch --depth 1 origin "$PINNED_COMMIT"
  git -C "$UPSTREAM_DIR" checkout --detach FETCH_HEAD
fi
actual_commit="$(git -C "$UPSTREAM_DIR" rev-parse HEAD)"
if [[ "$actual_commit" != "$PINNED_COMMIT" ]]; then
  echo "Unexpected Squirrel revision in $UPSTREAM_DIR" >&2
  echo "Expected: $PINNED_COMMIT" >&2
  echo "Found:    $actual_commit" >&2
  echo "Move that checkout aside and rerun this script; it will not reset local files." >&2
  exit 2
fi

controller="$UPSTREAM_DIR/sources/SquirrelInputController.swift"
project="$UPSTREAM_DIR/Squirrel.xcodeproj/project.pbxproj"
if ! grep -q 'private let superInputClient = SuperInputRerankClient()' "$controller" || \
   [[ ! -f "$UPSTREAM_DIR/sources/SuperInputRerankClient.swift" ]] || \
   ! grep -q 'SuperInputRerankClient.swift in Sources' "$project"; then
  git -C "$UPSTREAM_DIR" apply --check "$PATCH_FILE"
  git -C "$UPSTREAM_DIR" apply "$PATCH_FILE"
fi
if ! grep -q 'private let superInputClient = SuperInputRerankClient()' "$controller" || \
   [[ ! -f "$UPSTREAM_DIR/sources/SuperInputRerankClient.swift" ]] || \
   ! grep -q 'SuperInputRerankClient.swift in Sources' "$project" || \
   ! git -C "$UPSTREAM_DIR" apply --reverse --check "$PATCH_FILE"; then
  echo "The SuperInput Squirrel patch is incomplete." >&2
  exit 2
fi

# Install the upstream luna-pinyin recipe into the app bundle, then add the
# exact schema used by the rerank service and offline baseline.
(
  cd "$UPSTREAM_DIR"
  SQUIRREL_BUNDLED_RECIPES='luna-pinyin' ./action-install.sh
  make plum-data
  cp "$SCHEMA_FILE" data/plum/superpinyin.schema.yaml
  python3 - <<'PY'
from pathlib import Path
import re

path = Path("data/plum/default.yaml")
text = path.read_text(encoding="utf-8")
if not re.search(r"(?m)^\s*- schema: superpinyin\s*$", text):
    match = re.search(r"(?m)^schema_list:\s*\n((?:^[ \t]+- schema:.*\n)+)", text)
    if not match:
        raise SystemExit("Could not find schema_list in bundled default.yaml")
    text = text[:match.end(1)] + "  - schema: superpinyin\n" + text[match.end(1):]
    path.write_text(text, encoding="utf-8")
PY
  make release
)

app="$UPSTREAM_DIR/build/Build/Products/Release/Squirrel.app"
test -d "$app" || { echo "Expected app was not built: $app" >&2; exit 1; }
mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/SuperInput-Squirrel.app"
ditto "$app" "$OUTPUT_DIR/SuperInput-Squirrel.app"

if [[ "${1:-}" == "--pkg" ]]; then
  # make may consider a stale package target up to date; force this run to create it.
  rm -f "$UPSTREAM_DIR/package/Squirrel.pkg" "$OUTPUT_DIR/SuperInput-Squirrel.pkg"
  (
    cd "$UPSTREAM_DIR"
    make package
  )
  test -s "$UPSTREAM_DIR/package/Squirrel.pkg" || {
    echo "Package build did not create a fresh file: $UPSTREAM_DIR/package/Squirrel.pkg" >&2
    exit 1
  }
  cp "$UPSTREAM_DIR/package/Squirrel.pkg" "$OUTPUT_DIR/SuperInput-Squirrel.pkg"
  echo "Created unsigned installer package: $OUTPUT_DIR/SuperInput-Squirrel.pkg"
  echo "It installs the Squirrel bundle and may replace an existing Squirrel installation."
else
  echo "Created app bundle: $OUTPUT_DIR/SuperInput-Squirrel.app"
  echo "This is an unsigned local build; install it in /Library/Input Methods only after backing up any existing Squirrel.app."
  echo "To also create an unsigned installer package, rerun with --pkg."
fi
