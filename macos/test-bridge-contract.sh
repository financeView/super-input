#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if ! command -v swiftc >/dev/null 2>&1; then
  case "$(uname -s)" in
    Darwin)
      echo "swiftc is missing. Install Xcode or the Xcode Command Line Tools (xcode-select --install), then rerun this test." >&2
      ;;
    *)
      echo "swiftc is missing on $(uname -s). This test requires the Swift compiler; run it on macOS with Xcode Command Line Tools, or install a Swift toolchain." >&2
      ;;
  esac
  exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
swiftc \
  "$ROOT/macos/SuperInputRerankClient.swift" \
  "$ROOT/macos/tests/SuperInputClientContractTests.swift" \
  -o "$tmp/superinput-client-contract-tests"
"$tmp/superinput-client-contract-tests"
