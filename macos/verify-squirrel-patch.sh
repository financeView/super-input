#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMMIT="$(tr -d '[:space:]' < "$ROOT/macos/SQUIRREL_COMMIT")"
PATCH="$ROOT/macos/patches/squirrel-integration.patch"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone --filter=blob:none --no-checkout https://github.com/rime/squirrel.git "$tmp/squirrel"
git -C "$tmp/squirrel" fetch --depth 1 origin "$COMMIT"
git -C "$tmp/squirrel" checkout --detach FETCH_HEAD
git -C "$tmp/squirrel" apply --check "$PATCH"
echo "Squirrel patch applies cleanly to $COMMIT"
